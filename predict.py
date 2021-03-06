import argparse
import logging
import os
import cv2

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms

from unet import UNet
from utils.data_vis import plot_img_and_mask
from utils.dataset import BasicDataset


def predict_img(net,
                full_img,
                device,
                scale_factor=1,
                out_threshold=0.5):
    net.eval()

    img = torch.from_numpy(BasicDataset.preprocess(full_img, scale_factor))
    img = img.unsqueeze(0)
    img = img.to(device=device, dtype=torch.float32)

    with torch.no_grad():
        output = net(img)

        if net.n_classes > 1:
            probs = F.softmax(output, dim=1)
        else:
            probs = torch.sigmoid(output)

        probs = probs.squeeze(0)

        tf = transforms.Compose(
            [
                transforms.ToPILImage(),
                transforms.Resize(full_img.size[1]),
                transforms.ToTensor()
            ]
        )

        probs = tf(probs.cpu())
        full_mask = probs.squeeze().cpu().numpy()

    return full_mask > out_threshold


def get_args():
    parser = argparse.ArgumentParser(description='Predict masks from input images',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--model', '-m', default='MODEL.pth',
                        metavar='FILE',
                        help="Specify the file in which the model is stored")
    parser.add_argument('--input', '-i', metavar='INPUT', nargs='+',
                        help='filenames of input images', required=True)

    parser.add_argument('--output', '-o', metavar='INPUT', nargs='+',
                        help='Filenames of ouput images')
    parser.add_argument('--viz', '-v', action='store_true',
                        help="Visualize the images as they are processed",
                        default=False)
    parser.add_argument('--no-save', '-n', action='store_true',
                        help="Do not save the output masks",
                        default=False)
    parser.add_argument('--mask-threshold', '-t', type=float,
                        help="Minimum probability value to consider a mask pixel white",
                        default=0.5)
    parser.add_argument('--scale', '-s', type=float,
                        help="Scale factor for the input images",
                        default=1)
    parser.add_argument('--fps', '-f', type=int,
                        help="Numer of frames per second in the video to be generated",
                        default=58)

    return parser.parse_args()


def get_output_filenames(args):
    in_files = args.input
    out_files = []

    if not args.output:
        for f in in_files:
            pathsplit = os.path.splitext(f)
            out_files.append("{}_OUT{}".format(pathsplit[0], pathsplit[1]))
    elif len(in_files) != len(args.output):
        logging.error("Input files and output files are not of the same length")
        raise SystemExit()
    else:
        out_files = args.output

    return out_files


def mask_to_image(mask):
    return Image.fromarray((mask * 255).astype(np.uint8))


if __name__ == "__main__":
    args = get_args()
    in_files = args.input
    out_files = get_output_filenames(args)


    net = UNet(n_channels=3, n_classes=1)

    logging.info("Loading model {}".format(args.model))

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logging.info(f'Using device {device}')
    net.to(device=device)
    net.load_state_dict(torch.load(args.model, map_location=device))

    logging.info("Model loaded !")
 
    vidimages = []
    filelist = os.listdir(in_files[0])
    filename = filelist[0].split('_')[0]
    numfiles = len(filelist)
    max=0
    min=10000000000

    for i in range(numfiles):
        fn = filename + '_' + str(i) + '.png'
        logging.info("\nPredicting image {} ...".format(fn))

        img = Image.open(os.path.join(in_files[0], fn))
        count = 0
        mask = predict_img(net=net,
                           full_img=img,
                           scale_factor=args.scale,
                           out_threshold=args.mask_threshold,
                           device=device)
        for i in range (mask.shape[0]): 
            for j in range (mask.shape[1]): 
                if mask[i][j]:
                           count = count+1
        if count>max:
               max = count
        if count<min:
               min = count


        if not args.no_save:
            os.makedirs('./out/', exist_ok=True) 
            out_fn = './out/' + fn
            result = mask_to_image(mask)
            result.save(out_fn)

            logging.info("Mask saved to {}".format(out_fn))

            img = cv2.imread(os.path.join(in_files[0], fn))
            overlay = np.zeros(img.shape, np.uint8)
            overlay[mask>0] = (0,0,255)
            added_image = cv2.addWeighted(img,0.9,overlay,0.2,0)
            os.makedirs('./overlay/', exist_ok=True)
            cv2.imwrite('overlay/' + fn, added_image)
            vidimages.append(added_image)

        if args.viz:
            logging.info("Visualizing results for image {}, close to continue ...".format(fn))
            plot_img_and_mask(img, mask)

    video = cv2.VideoWriter(filename + '_over.avi',cv2.VideoWriter_fourcc(*'mp4v'), args.fps, (112,112))
    sol = ((max-min)/max)*100
    #print("Ejection Fraction is:")
    print(sol)
 
    for i in range(len(vidimages)):
       video.write(vidimages[i])
    video.release()
