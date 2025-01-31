# -*- coding: utf-8 -*-
"""model_training_2.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1uOVZtV3Mc1j-vySS6bxYbIaxEmPDQr2u
"""

import os
import sys
import cv2
import numpy as np
import matplotlib.pyplot as plt
import torch
from PIL import Image
from glob import glob
from torchvision import transforms
import rasterio

# Step 1: Import Required Libraries
# (Assuming all necessary libraries are already installed)

# Add SuperGluePretrainedNetwork to the system path
sys.path.append('./SuperGluePretrainedNetwork')

# Import Matching Modules
from models.matching import Matching
from models.utils import read_image, make_matching_plot

# Step 2: Define Helper Functions
def find_image_pairs(data_dir):
    images_by_tile = {}
    for root, dirs, files in os.walk(data_dir):
        for file in files:
            if file.endswith('.jp2'):
                filepath = os.path.join(root, file)
                filename = os.path.basename(filepath)
                parts = filename.split('_')
                if len(parts) >= 3:
                    tile = parts[0]
                    date = parts[1][:8]  # YYYYMMDD
                    band_part = parts[-1]
                    band = band_part.split('.')[0]
                    key = (tile, date)
                    if key not in images_by_tile:
                        images_by_tile[key] = {}
                    images_by_tile[key][band] = filepath

    tile_dates = {}
    for (tile, date), bands in images_by_tile.items():
        if tile not in tile_dates:
            tile_dates[tile] = []
        tile_dates[tile].append((date, bands))
    for tile in tile_dates:
        tile_dates[tile].sort()

    image_pairs = []
    for tile in tile_dates:
        dates_bands = tile_dates[tile]
        for i in range(len(dates_bands) - 1):
            date1, bands1 = dates_bands[i]
            date2, bands2 = dates_bands[i+1]
            required_bands = {'B02', 'B03', 'B04'}
            if required_bands.issubset(bands1.keys()) and required_bands.issubset(bands2.keys()):
                image_pairs.append(((bands1['B02'], bands1['B03'], bands1['B04']),
                                    (bands2['B02'], bands2['B03'], bands2['B04'])))
    return image_pairs

def load_sentinel2_image(band_paths):
    try:
        with rasterio.open(band_paths[0]) as blue_src, \
             rasterio.open(band_paths[1]) as green_src, \
             rasterio.open(band_paths[2]) as red_src:
            blue = blue_src.read(1)
            green = green_src.read(1)
            red = red_src.read(1)
            image = np.stack((red, green, blue), axis=-1)
            image_gray = cv2.cvtColor((image / np.max(image) * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
            return image_gray, image
    except Exception as e:
        print(f'Error loading bands: {e}')
        return None, None

# Step 3: Main Function to Perform Feature Matching
def main():
    # Step 3.1: Load and Preprocess Images
    data_dir = '/path/to/your/dataset'  # Update this path to your dataset directory
    image_pairs = find_image_pairs(data_dir)

    # Check if any image pairs were found
    if not image_pairs:
        print("No image pairs found in the specified directory.")
        return

    # Select a pair of images to process (you can loop over all pairs if desired)
    (band_paths1), (band_paths2) = image_pairs[0]
    image0_gray, image0_color = load_sentinel2_image(band_paths1)
    image1_gray, image1_color = load_sentinel2_image(band_paths2)

    if image0_gray is None or image1_gray is None:
        print("Error loading images.")
        return

    # Resize images for processing
    image0_gray = cv2.resize(image0_gray, (640, 480))
    image1_gray = cv2.resize(image1_gray, (640, 480))

    # Step 3.2: Configure and Run the Matching Model
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    config = {
        'superpoint': {
            'nms_radius': 4,
            'keypoint_threshold': 0.005,
            'max_keypoints': 1024,
        },
        'superglue': {
            'weights': 'outdoor',
            'sinkhorn_iterations': 20,
            'match_threshold': 0.2,
        }
    }
    matching = Matching(config).eval().to(device)

    inp0 = torch.from_numpy(image0_gray / 255.).float()[None, None].to(device)
    inp1 = torch.from_numpy(image1_gray / 255.).float()[None, None].to(device)
    with torch.no_grad():
        pred = matching({'image0': inp0, 'image1': inp1})
    keypoints0 = pred['keypoints0'][0].cpu().numpy()
    keypoints1 = pred['keypoints1'][0].cpu().numpy()
    matches = pred['matches0'][0].cpu().numpy()
    confidence = pred['matching_scores0'][0].cpu().numpy()

    # Step 3.3: Filter and Visualize Matches
    valid = matches > -1
    mkpts0 = keypoints0[valid]
    mkpts1 = keypoints1[matches[valid]]
    mconf = confidence[valid]

    color = plt.cm.jet(mconf)

    # Create output directory if it doesn't exist
    output_dir = './output'
    os.makedirs(output_dir, exist_ok=True)

    # Generate the matching plot
    output_path = os.path.join(output_dir, 'matches.png')
    make_matching_plot(
        image0_gray,
        image1_gray,
        keypoints0, keypoints1, mkpts0, mkpts1, color,
        text=['SuperGlue Feature Matching', f'Keypoints: {len(keypoints0)}:{len(keypoints1)}', f'Matches: {len(mkpts0)}'],
        path=output_path, show_keypoints=True, opencv_display=False
    )
    print(f"Matching visualization saved to {output_path}")

if __name__ == '__main__':
    main()