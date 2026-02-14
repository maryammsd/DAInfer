import json

# File paths
file1_path = "/home/maryam/clearblue/source-code/DAInfer/data/output/compareResult/llm_autoPrompt_FourTypes_5_5_0.8_1.0-embed-small/inferredCorrectSpecs.json"
file2_path = "/home/maryam/clearblue/source-code/DAInfer/data/output/compareResult/autoPrompt_FourTypes_1_5_1.0_0.7/inferredCorrectSpecs.json"

# Load the data from the files
with open(file1_path, "r") as f1, open(file2_path, "r") as f2:
    data1 = json.load(f1)  # Load data from file1
    data2 = json.load(f2)  # Load data from file2

# Convert nested lists to tuples
set1 = set(tuple(item) for item in data1)
set2 = set(tuple(item) for item in data2)

# Find differences
only_in_file1 = set1 - set2  # Elements in file1 but not in file2
only_in_file2 = set2 - set1  # Elements in file2 but not in file1

# Print the results
print("Elements only in file1:")
for item in only_in_file1:
    print(item)
print("\n")

print("\nElements only in file2:")
for item in only_in_file2:
    print(item)

print("Number of diffs for file 1:", len(only_in_file1))
print("Number of diffs for file 2:", len(only_in_file2))