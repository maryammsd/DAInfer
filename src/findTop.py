import json
import os


def load_specs_from_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v
        raise ValueError(f"No list found in JSON object at {path}")
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported JSON format in {path}: must be list or dict of list entries")

def find_top_spec(data, n):
    specs = {}

    for spec in data:
        key = spec[0]  # Assuming the first element is a unique identifier
        if key not in specs:
            specs[key] = 0
        count = specs[key] + 1
        specs[key] = count
    
    # print max count for debugging
    max_count = max(specs.values())
    print("Max Count:", max_count)
    # Find the top n specs
    sorted_specs = sorted(specs.items(), key=lambda item: item[1], reverse=True)
    top_n_keys = [key for key, count in sorted_specs[:n]]

    # Map keys back to their original specs
    top_n_specs = {key: specs[key] for key in top_n_keys}
    return top_n_specs


def exit_file(path: str) -> bool:
    return os.path.isfile(path)

def __main__():
    json_path = "/home/maryam/clearblue/source-code/DAInfer/data/oracle/ManualOracle/dataflowSpecs.json"
    data = load_specs_from_json(json_path)
    top_spec = find_top_spec(data, n=50)
    
    i = 1
    sum = 0
    for key in top_spec:
        file_path = "/home/maryam/clearblue/source-code/DAInfer/data/javadoc/benchmark-dainfer+/" + key + ".json"
        if exit_file(file_path):
            continue
        print("", i, ": Top Spec:", key, " Count:", top_spec[key])
        i += 1
        sum += top_spec[key]

    print("Total Count:", sum)

if __name__ == "__main__":
    __main__()