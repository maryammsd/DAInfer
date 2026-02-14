import json
import os
import re
import helper 

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

def extract_simple_class_name(fqcn: str) -> str:
    #return fqcn 
    return fqcn.strip().split('.')[-1]

def extract_method_info(signature: str):
    match = re.search(r"(\w+)\s*\((.*?)\)", signature)
    if match:
        name = match.group(1)
        params = match.group(2).strip()
        if not params:
            return name, 0
        return name, len([p.strip() for p in params.split(',') if p.strip()])
    return signature.strip(), 0

def load_labeled_classes(labeled_classes_path: str):
    with open(labeled_classes_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return set(data.get("labeledClasses", []))

def compare_specs_alias(candidate_file: str, oracle_file: str, labeled_classes_file: str, output_dir: str) -> None:
    candidates = load_specs_from_json(candidate_file)
    oracles = load_specs_from_json(oracle_file)
    labeled_classes = load_labeled_classes(labeled_classes_file)

    correct = []
    wrong = []
    missing = []
    oracle_index = {}
    for o in oracles:
        full_cls_name = o[0]
        if full_cls_name not in labeled_classes:
            print(f"Skipping oracle spec for unlabeled class: {full_cls_name} ")
            continue
        cls_name = extract_simple_class_name(full_cls_name)
        method1 = extract_method_info(o[1])
        method2 = extract_method_info(o[2])

        mapping = o[3]
        key = (full_cls_name, method1, method2, mapping)
        print(f"key is {key} for oracle spec with full class name {full_cls_name} and method1 {method1} and method2 {method2} and mapping {mapping}.")
        print(f"Mapping loaded for oracle spec: {key} ")
        oracle_index[key] = True
    
    for spec in candidates:
        full_cls_name = spec[1]
        if full_cls_name not in labeled_classes:
            continue
        #print(f"spec 2: {spec[2]}.")

        cls_name = extract_simple_class_name(full_cls_name)
        method1 = extract_method_info(spec[2])
        method2 = extract_method_info(spec[3])
        mapping = spec[6]
        key = (full_cls_name, method1, method2, mapping)

        if key in oracle_index:
            correct.append(key)
        else:
            print(f"Candidate spec not found in oracle: {key} ")
            wrong.append(key)

            
    

    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, 'inferredCorrectSpecs.json'), 'w', encoding='utf-8') as f:
        json.dump(correct, f, indent=2, ensure_ascii=False)
    with open(os.path.join(output_dir, 'inferredWrongSpecs.json'), 'w', encoding='utf-8') as f:
        json.dump(wrong, f, indent=2, ensure_ascii=False)
    with open(os.path.join(output_dir, 'inferredMissingSpecs.json'), 'w', encoding='utf-8') as f:
        json.dump(missing, f, indent=2, ensure_ascii=False)

    print(f"There are {len(correct)} correct and {len(wrong)} wrong specs after filtering labeled classes.")
    print(f" Number of oracle specs considered: {len(oracle_index.items())} ")
    print(f" Number of candidates considered: {len(candidates)} ")
    print(f" Missing specs: {len(missing)}")
    tp = len(correct) 
    fp = len(wrong) 
    fn = 984 - tp-fp
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    accuracy = (tp ) / (tp + fp + fn ) if (tp + fp + fn ) > 0 else 0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    print(f" Accuracy: {accuracy:.4f} ")
    print(f" Recall: {recall:.4f} ")
    print(f" Precision: {precision:.4f} ")
    print(f" F1 Score: {f1_score:.4f} ")
    print(f" True Positives: {tp} ")
    print(f" False Positives: {fp} ")
    print(f" False Negatives: {fn} ")

def splitMethodFromLabelledData(signature: str):
    # fomrat is like: java.lang.String getDeviceId(java.object.Object)
    init_string = signature.split(" ")
    if len(init_string) < 1:
        return None, None, None
    return_type_all = init_string[0]
    if "." in return_type_all:
        return_type = return_type_all.split(".")[-1]
    else:
        return_type = return_type_all
    rest_signature = " ".join(init_string[1:])
    method_name = rest_signature[0 : rest_signature.find("(")]
    para_list_str = rest_signature[rest_signature.find("(") + 1 : rest_signature.find(")")]
    print(f" para list str: {para_list_str} for method {method_name} in signature {signature}")
    para_list = []
    if para_list_str.strip() != "":
        if len(para_list_str) == 1:
            print(f" only one param string: {para_list_str} for method {method_name} in signature {signature}")
        para_list_tmp = para_list_str.split(",")
        print(f" param list tmp: {para_list_tmp} for method {method_name} in signature {signature}")
        if para_list_str.strip() == "":
            if len(para_list_str) == 0:
                para_list = None
            elif len(para_list_str) == 1:
                para_list = str(para_list_str[0])
                print(f" only one param: {para_list_str} for method {method_name} in signature {signature}")
                return return_type, method_name, para_list
       
        for para in para_list_tmp:
            para = para.strip()
            if "." in para:
                para_type = para.split(".")[-1]
            else:
                para_type = para
            para_list.append(para_type)
    else:
        print(f" no param for method {method_name} in signature {signature}")
    if return_type == "T":
        return_type = "Object"
    return return_type, method_name, para_list

def compare_specs_dataflow(candidate_file: str, oracle_file: str, labeled_classes_file: str, output_dir: str) -> None:
    candidates = load_specs_from_json(candidate_file)
    oracles = load_specs_from_json(oracle_file)
    labeled_classes = load_labeled_classes(labeled_classes_file)
    number_of_oracle_specs = 0
    correct = []
    wrong = []
    missing = []
    methods = []
    classes = []
    oracle_index = {}
    for o in oracles:
        full_cls_name = o[0]
        #print(f"Oracle spec class: {full_cls_name} ")
        if full_cls_name not in labeled_classes:
            print(f"Skipping oracle spec for unlabeled class: {full_cls_name} ")
            continue
        method = o[1]
        print(f"Oracle spec method: {method} ") 
        return_type, method_name, para_list = splitMethodFromLabelledData(method)
        if para_list is None:
            method = f"{return_type} {method_name}()"
        else:
            if len(para_list) != 1:
                method = f"{return_type} {method_name}({', '.join(para_list)})"
            else:
                method = f"{return_type} {method_name}({para_list[0]})"
        label = o[2]
        key = (full_cls_name, method.lower(), label.lower())
        print(f"Mapping loaded for oracle spec: {key} ")
        oracle_index[key] = True

    for spec in candidates:
        full_cls_name = spec[0]
        if full_cls_name not in labeled_classes:
            continue
    

        method = spec[2]
        return_type, method_name, para_list, para_names = helper.splitMethodSignatureFromJavaDoc(method)
        if para_list is None:
            method = f"{return_type} {method_name}()"
        else:
            method = f"{return_type} {method_name}({', '.join(para_list)})"
        if method not in methods:
            methods.append(method)
        if full_cls_name not in classes:
            classes.append(full_cls_name)
        label = spec[3]
        method = method.lower()
        labels = []
        if label == "source-sink" or label == "sink-source":
            labels = ["source", "sink"]
        else:
            labels = [label]
        
        for label in labels:
            key = (full_cls_name, method, label.lower())
            print(f"Comparing candidate spec key: {key} ")
            if key in oracle_index:
                correct.append(key)
            else:
                wrong.append(key)
                
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, 'inferredCorrectSpecs.json'), 'w', encoding='utf-8') as f:
        json.dump(correct, f, indent=2, ensure_ascii=False)
    with open(os.path.join(output_dir, 'inferredWrongSpecs.json'), 'w', encoding='utf-8') as f:
        json.dump(wrong, f, indent=2, ensure_ascii=False)
    with open(os.path.join(output_dir, 'inferredMissingSpecs.json'), 'w', encoding='utf-8') as f:
        # missing will be the keys in oracle_index that are not in correct 
        for key in oracle_index.keys():
            if key not in correct:
                class_name = key[0]
                if class_name not in labeled_classes:
                    print(f"Skipping missing oracle spec for unlabeled class: {class_name} ")
                    continue
                missing.append(key)
        json.dump(missing, f, indent=2, ensure_ascii=False)

    print(f"There are {len(correct)} correct and {len(wrong)} wrong specs after filtering labeled classes.")
    print(f" Number of oracle specs considered: {len(oracle_index.items())} ")
    print(f" Number of candidates considered: {len(candidates)} ")
    print(f" Specs analyzed but not in labelled dataset: {len(missing)}")
    print(f" Methods analyzed: {len(methods)} ")
    print(f" Classes analyzed: {len(classes)} ")
    tp = len(correct) 
    fp = len(wrong) 
    fn = 1372 - tp
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    accuracy = (tp ) / (tp + fp + fn ) if (tp + fp + fn ) > 0 else 0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    print(f" Accuracy: {accuracy:.4f} ")
    print(f" Recall: {recall:.4f} ")
    print(f" Precision: {precision:.4f} ")
    print(f" F1 Score: {f1_score:.4f} ")
    print(f" True Positives: {tp} ")
    print(f" False Positives: {fp} ")
    print(f" False Negatives: {fn} ")

if __name__ == '__main__':
    candidate_path = '/home/maryam/clearblue/source-code/DAInfer/data/output/alias-llm_autoPrompt_FourTypes_5_2_0.8_1.0-e5-large/inferResult/benchmark_inferredSpecs.json' # benchmark_inferredSourceSinkSpecs or benchmark_inferredDataflowSpec or benchmark_inferredSpecs (alias)
    # sample LLM and embedding model LLM-qwen-non-cache-source-sink-5-10 sentencebert-source-sink-12-5
    oracle_path = '/home/maryam/clearblue/source-code/DAInfer/data/oracle/ManualOracle/labeledOracleSpecs.json' # alias  labeledOracleSpecs dataflow dataflowSpecs
    labeled_classes_path = '/home/maryam/clearblue/source-code/DAInfer/data/oracle/ManualOracle/labeledClasses.json' # alias labeledClasses.json dataflow labeledClasses_dataflow
    output_directory = '/home/maryam/clearblue/source-code/DAInfer/data/output/compareResult/alias-llm_autoPrompt_FourTypes_5_2_0.8_1.0-e5-large/'
    if not "dataflow" in oracle_path:
        print("----------- compare alias specs ------------")
        compare_specs_alias(candidate_path, oracle_path, labeled_classes_path, output_directory)
    else:
        print("----------- compare dataflow specs ------------")
        compare_specs_dataflow(candidate_path, oracle_path, labeled_classes_path, output_directory)
