import os
import json

def compare_memoryTypeFeatures(autoPrompt_dir, llm_autoPrompt_dir, log_file):
    """
    Compare memoryTypeFeature.json files between two directories and log the differences.

    Args:
        autoPrompt_dir (str): Path to the autoPrompt_fourtypes directory.
        llm_autoPrompt_dir (str): Path to the llm_autoPrompt_fourTypes directory.
        log_file (str): Path to the log file where differences will be saved.
    """
    # Define the label mapping
    label_mapping = {
        "memory read": "read",
        "memory write": "set",
        "insertion upon memory": "insert",
        "deletion upon memory": "remove"
    }

    differences = {}

    # Iterate through all packages in the autoPrompt directory
    for package in os.listdir(autoPrompt_dir):
        autoPrompt_package_path = os.path.join(autoPrompt_dir, package)
        llm_autoPrompt_package_path = os.path.join(llm_autoPrompt_dir, package)

        # Check if the package exists in both directories
        if os.path.isdir(autoPrompt_package_path) and os.path.isdir(llm_autoPrompt_package_path):
            autoPrompt_file = os.path.join(autoPrompt_package_path, "memoryTypeFeature.json")
            llm_autoPrompt_file = os.path.join(llm_autoPrompt_package_path, "memoryTypeFeature_embedding_model.json")

            # Check if both files exist
            if os.path.exists(autoPrompt_file) and os.path.exists(llm_autoPrompt_file):
                # Load the JSON files
                with open(autoPrompt_file, "r") as f1, open(llm_autoPrompt_file, "r") as f2:
                    autoPrompt_data = json.load(f1)
                    llm_autoPrompt_data = json.load(f2)

                # Compare the JSON data
                package_differences = {}
                for method, autoPrompt_features in autoPrompt_data.items():
                    if method in llm_autoPrompt_data:
                        llm_features = llm_autoPrompt_data[method]
                        method_differences = {}

                        # Compare features using the label mapping
                        for auto_label, llm_label in label_mapping.items():
                            auto_value = autoPrompt_features.get(auto_label, "MISSING")
                            llm_value = llm_features.get(llm_label, "MISSING")

                            if auto_value != llm_value:
                                method_differences[auto_label] = {
                                    "autoPrompt": auto_value,
                                    "llm_autoPrompt": llm_value
                                }

                        if method_differences:
                            package_differences[method] = method_differences
                    else:
                        # Method is missing in llm_autoPrompt
                        package_differences[method] = {
                            "autoPrompt": autoPrompt_features,
                            "llm_autoPrompt": "MISSING"
                        }

                if package_differences:
                    differences[package] = package_differences

    # Write the differences to the log file
    with open(log_file, "w") as log:
        json.dump(differences, log, indent=4)
    
    print(f"Number of packages with differences: {len(differences)}")
    print(f"Total differences found: {sum(len(v) for v in differences.values())}")
    print(f"Differences logged to {log_file}")


# Paths to the directories
autoPrompt_dir = "/home/maryam/clearblue/source-code/DAInfer/data/output/autoPrompt_FourTypes_5_1_1.3_0.7/methodInfo/benchmark"
llm_autoPrompt_dir = "/home/maryam/clearblue/source-code/DAInfer/data/output/llm_autoPrompt_FourTypes_5_5_1.0_1.0-embed-small/methodInfo/benchmark"
log_file = "/home/maryam/clearblue/source-code/DAInfer/data/output/differences_log.json"

# Run the comparison
compare_memoryTypeFeatures(autoPrompt_dir, llm_autoPrompt_dir, log_file)