import os

def find_missing_json_files(benchmark_dir, output_dir):
    """
    Find folder names in output_dir that don't have corresponding JSON files in benchmark_dir.
    
    Args:
        benchmark_dir (str): Path to the benchmark directory containing JSON files.
        output_dir (str): Path to the output directory containing folders.
    
    Returns:
        list: List of folder names without corresponding JSON files.
    """
    len_benchmark = len(os.listdir(benchmark_dir))
    len_output = len(os.listdir(output_dir))
    print(f"Number of files in benchmark: {len_benchmark}")
    print(f"Number of folders in output: {len_output}")
    # Get list of JSON files in benchmark (without extension)
    json_files = set()
    for filename in os.listdir(benchmark_dir):
        if filename.endswith('.json'):
            #print(f"Found JSON file: {filename[:-5].lower()}")
            json_files.add(filename[:-5].lower())  # Remove .json extension

    # Get list of folders in output
    folders = set()
    for name in os.listdir(output_dir):
        if os.path.isdir(os.path.join(output_dir, name)):
            #print(f"Found folder: {name.lower()}")
            folders.add(name.lower())

    # Find folders without corresponding JSON files
    missing = folders - json_files
    print(f"Number of folders without corresponding JSON files: {len(missing)}")
    print(f"Number of Existing JSON files: {len(json_files)}")

    
    return sorted(list(missing))


# Example usage
if __name__ == "__main__":
    benchmark_dir = "/home/maryam/clearblue/source-code/DAInfer/data/javadoc/benchmark-dainfer+"
    output_dir = "/home/maryam/clearblue/source-code/DAInfer/data/javadoc/benchmark-dataflowspec/output"
    
    missing_folders = find_missing_json_files(benchmark_dir, output_dir)
    
    #print(f"Folders in 'output' without corresponding JSON in 'benchmark': {len(missing_folders)}")
    print("-" * 60)
    for folder in missing_folders:
        print(f"  {folder}")