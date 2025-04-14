import torch

def main():
    # Check if CUDA is available
    cuda_available = torch.cuda.is_available()
    print("CUDA available:", cuda_available)

    if cuda_available:
        # Print CUDA version (the version of the CUDA toolkit that PyTorch was built with)
        print("CUDA version:", torch.version.cuda)

        # Print the number of available GPUs and the name of the first GPU
        num_gpus = torch.cuda.device_count()
        print("Number of GPUs:", num_gpus)
        if num_gpus > 0:
            print("GPU 0 name:", torch.cuda.get_device_name(0))

    # Check cuDNN settings
    print("cuDNN enabled:", torch.backends.cudnn.enabled)
    cudnn_version = torch.backends.cudnn.version()
    print("cuDNN version:", cudnn_version)

if __name__ == "__main__":
    main()
