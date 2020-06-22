# coding: utf8

"""
This file generates data for trivial or intractable (random) data for binary classification.
"""
import pandas as pd
import numpy as np
import nibabel as nib
from os import path
import os
import torch.nn.functional as F
import torch
from .utils import im_loss_roi_gaussian_distribution, find_image_path
from ..tsv.tsv_utils import baseline_df
from clinicadl.tools.inputs.filename_types import FILENAME_TYPE


def generate_random_dataset(caps_dir, tsv_path, output_dir, n_subjects, mean=0, 
                            sigma=0.5, preprocessing="linear", output_size=None):

    """
    Generates a random dataset.
    
    Creates a random dataset for intractable classification task from the first
    subject of the tsv file (other subjects/sessions different from the first
    one are ignored. Degree of noise can be parameterized.

    Args:
        caps_dir: (str) Path to the (input) CAPS directory.
        tsv_path: (str) path to tsv file of list of subjects/sessions.
        output_dir: (str) folder containing the synthetic dataset in (output)
            CAPS format.  
        n_subjects: (int) number of subjects in each class of the
            synthetic dataset
        mean: (float) mean of the gaussian noise
        sigma: (float) standard deviation of the gaussian noise
        preprocessing: (str) preprocessing performed. Must be in ['linear', 'extensive'].
        output_size: (tuple[int]) size of the output. If None no interpolation
             will be performed.
    
    Returns:
        A folder written on the output_dir location (in CAPS format), also a
        tsv file describing this output

    Raises:

    """
    # Read DataFrame
    data_df = pd.read_csv(tsv_path, sep='\t')

    # Create subjects dir
    if not path.exists(path.join(output_dir, 'subjects')):
        os.makedirs(path.join(output_dir, 'subjects'))

    # Retrieve image of first subject
    participant_id = data_df.loc[0, 'participant_id']
    session_id = data_df.loc[0, 'session_id']

    image_path = find_image_path(caps_dir, participant_id, session_id, preprocessing)
    image_nii = nib.load(image_path)
    image = image_nii.get_data()

    # Create output tsv file
    participant_id_list = ['sub-RAND%i' % i for i in range(2 * n_subjects)]
    session_id_list = ['ses-M00'] * 2 * n_subjects
    diagnosis_list = ['AD'] * n_subjects + ['CN'] * n_subjects
    data = np.array([participant_id_list, session_id_list, diagnosis_list])
    data = data.T
    output_df = pd.DataFrame(data, columns=['participant_id', 'session_id', 'diagnosis'])
    output_df['age'] = 60
    output_df['sex'] = 'F'
    output_df.to_csv(path.join(output_dir, 'data.tsv'), sep='\t', index=False)

    for i in range(2 * n_subjects):
        gauss = np.random.normal(mean, sigma, image.shape)
        participant_id = 'sub-RAND%i' % i
        noisy_image = image + gauss
        if output_size is not None:
            noisy_image_pt = torch.Tensor(noisy_image[np.newaxis, np.newaxis, :])
            noisy_image_pt = F.interpolate(noisy_image_pt, output_size)
            noisy_image = noisy_image_pt.numpy()[0, 0, :, :, :]
        noisy_image_nii = nib.Nifti1Image(noisy_image, header=image_nii.header, affine=image_nii.affine)
        noisy_image_nii_path = path.join(output_dir, 'subjects', participant_id, 'ses-M00', 't1_linear')
        noisy_image_nii_filename = participant_id + '_ses-M00' + FILENAME_TYPE['cropped'] + '.nii.gz'
        if not path.exists(noisy_image_nii_path):
            os.makedirs(noisy_image_nii_path)
        nib.save(noisy_image_nii, path.join(noisy_image_nii_path, noisy_image_nii_filename))


def generate_trivial_dataset(caps_dir, tsv_path, output_dir, n_subjects, preprocessing="linear",
                             mask_path=None, atrophy_percent=60, output_size=None, group=None):
    """
    Generates a fully separable dataset.

    Generates a dataset, based on the images of the CAPS directory, where a
    half of the image is processed using a mask to oclude a specific region.
    This procedure creates a dataset fully separable (images with half-right
    processed and image with half-left processed)
    
    Args:
        caps_dir: (str) path to the CAPS directory.
        tsv_path: (str) path to tsv file of list of subjects/sessions.
        output_dir: (str) folder containing the synthetic dataset in CAPS format.
        n_subjects: (int) number of subjects in each class of the synthetic
            dataset.
        preprocessing: (str) preprocessing performed. Must be in ['linear', 'extensive'].
        mask_path: (str) path to the extracted masks to generate the two labels.
        atrophy_percent: (float) percentage of atrophy applied.
        output_size: (tuple[int]) size of the output. If None no interpolation
            will be performed.
        group: (str) group used for dartel preprocessing.
        
    Returns:
        Folder structure where images are stored in CAPS format.
    
    Raises:    
    """

    # Read DataFrame
    data_df = pd.read_csv(tsv_path, sep='\t')
    data_df = baseline_df(data_df, "None")

    if n_subjects > len(data_df):
        raise ValueError("The number of subjects %i cannot be higher than the number of subjects in the baseline "
                         "DataFrame extracted from %s" % (n_subjects, tsv_path))

    if mask_path is None:
        raise ValueError('Please provide a path to masks. Such masks are available at '
                         'clinicadl/tools/data/AAL2.')

    # Output tsv file
    columns = ['participant_id', 'session_id', 'diagnosis', 'age', 'sex']
    output_df = pd.DataFrame(columns=columns)
    diagnosis_list = ["AD", "CN"]

    for i in range(2 * n_subjects):
        data_idx = i // 2
        label = i % 2

        participant_id = data_df.loc[data_idx, "participant_id"]
        session_id = data_df.loc[data_idx, "session_id"]
        filename = ['sub-TRIV%i' + FILENAME_TYPE['cropped'] + '.nii.gz'] % i
        path_image = os.path.join(output_dir, 'subjects', 'sub-TRIV%i' % i, 'ses-M00', 't1_linear')

        if not os.path.exists(path_image):
            os.makedirs(path_image)

        image_path = find_image_path(caps_dir, participant_id, session_id, preprocessing, group)
        image_nii = nib.load(image_path)
        image = image_nii.get_data()

        atlas_to_mask = nib.load(os.path.join(mask_path, 'mask-%i.nii' % (label + 1))).get_data()

        # Create atrophied image
        trivial_image = im_loss_roi_gaussian_distribution(image, atlas_to_mask, atrophy_percent)
        if output_size is not None:
            trivial_image_pt = torch.Tensor(trivial_image[np.newaxis, np.newaxis, :])
            trivial_image_pt = F.interpolate(trivial_image_pt, output_size)
            trivial_image = trivial_image_pt.numpy()[0, 0, :, :, :]
        trivial_image_nii = nib.Nifti1Image(trivial_image, affine=image_nii.affine)
        trivial_image_nii.to_filename(os.path.join(path_image, filename))

        # Append row to output tsv
        row = ['sub-TRIV%i' % i, 'ses-M00', diagnosis_list[label], 60, 'F']
        row_df = pd.DataFrame([row], columns=columns)
        output_df = output_df.append(row_df)

    output_df.to_csv(path.join(output_dir, 'data.tsv'), sep='\t', index=False)
