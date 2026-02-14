import os
import sys
import xml.etree.ElementTree as ET
import json
import helper as helper
import re
from typing import Dict, List
from xml.dom import minidom
import type as type_module

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

def parse_access_path(elem: ET.Element) -> str:
    """Return AccessPath text if present, else None."""
    return elem.attrib.get("AccessPath", "")

def parse_flow(flow_elem: ET.Element) -> Dict[str, List[Dict]]:
    """Parse a single <flow> element and return dict with from/to info."""
    alias = flow_elem.attrib.get("isAlias", "false").lower() == "true"
    entry = {"from": [], "to": [], "isAlias": alias}
    # <from> elements
    for f in flow_elem.findall("from"):
        entry["from"].append({
            "sourceSinkType": f.attrib.get("sourceSinkType"),
            "AccessPath": parse_access_path(f),
        })
    # <to> elements
    for t in flow_elem.findall("to"):
        entry["to"].append({
            "sourceSinkType": t.attrib.get("sourceSinkType"),
            "AccessPath": parse_access_path(t),
        })
    return entry

def splitMethodFromLabelledData(signature: str):
    # fomrat is like: java.lang.String getDeviceId(java.object.Object)
    init_string = signature.split(" ")
    if len(init_string) < 1:
        return None, None, None
    return_type_all = init_string[0]
    return_type = return_type_all
    #if "." in return_type_all:
    #    return_type = return_type_all.split(".")[-1]
    #else:
    #    return_type = return_type_all
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

def parse_xml_file(path: str) -> Dict[str, List[Dict]]:
    """Parse the XML and return a dictionary of flows."""
    tree = ET.parse(path)
    root = tree.getroot()
    flows = []

    for method in root.findall(".//method"):
        method_id = method.attrib.get("id")
        flows_parent = method.find("flows")
        if flows_parent is not None:
            flows.append({"method_id": method_id, "flows": []})
            for flow in flows_parent.findall("flow"):
                flows[-1]["flows"].append(parse_flow(flow))

    return flows

def get_first_item(lst, key, default=None):
    """
    Safely get a value from the first item in a list of dictionaries.
    
    Args:
        lst (list): List of dictionaries.
        key (str): Key to retrieve from the first dictionary.
        default: Default value if not found.
    
    Returns:
        The value or default.
    """
    if lst and isinstance(lst, list) and len(lst) > 0:
        print(f"Accessing key '{key}' from first item: {lst[0]}")  # Debug statement
        return lst[0].get(key, default)
    return default

def classify_sources_sinks(flows: List[Dict]) -> Dict[str, Dict[str, List[str]]]:
    """Classify sources and sinks from the flows, keeping only method IDs."""
    sources = []
    sinks = []


    for flow in flows:
        print(f"Processing flow: {flow}")  # Debug statement
        method_id = flow.get("method_id")
        flow_entries = flow.get("flows", [])
        print(f"----------------------------------     Method ID: {method_id}")  # Debug statement
        print(f"Flow Entries: {flow_entries}")  # Debug statement
        print(f" Flow entry  with method_id {flow}")
        for entry in flow_entries:

            # two types of values for from: Field or Parameter
            # two types of values for to: Return or Field
            from_type = get_first_item(entry.get("from", []), "sourceSinkType")
            to_type = get_first_item(entry.get("to", []), "sourceSinkType")
            alias_info = get_first_item(entry.get("isAlias", False), "isAlias", False)

            print(f"  From type: {from_type}, To type: {to_type}, Is Alias: {alias_info}")  # Debug statement

            if from_type in {"Field"} and to_type in {"Return","Parameter"}:
                if method_id not in sources:
                    sources.append(method_id)
                    print(f"   Added to sources: {method_id}")  # Debug statement
            

            if from_type in {"Parameter","Return"} and to_type in {"Field"}:
                if method_id not in sinks:
                    sinks.append(method_id)
                    print(f"   Added to sinks: {method_id}")  # Debug statement

                
    return {"sources": sources, "sinks": sinks}


def process_xml_folder(input_dir: str) -> None:
    """Process all XML files in the input directory and save sources and sinks."""
    json_data = []
    labeled_classes = set()
    for filename in os.listdir(input_dir):
        if filename.endswith(".xml"):
            file_path = os.path.join(input_dir, filename)

            flows = parse_xml_file(file_path)
            classified = classify_sources_sinks(flows)

            # Create an output directory for each XML file
            base_name = os.path.splitext(filename)[0]
            labeled_classes.add(base_name)

            for source in classified['sources']:
                json_data.append([base_name, source, "SOURCE"])
            for sink in classified['sinks']:
                json_data.append([base_name, sink, "SINK"])
    
    return json_data, labeled_classes

def refine_type_name(type_name: str) -> str:
  
    if type_name == "T" or type_name == "Object":
        return "java.lang.Object"
    elif type_name == "Object[]":
        return "java.lang.Object[]"
    elif type_name == "V" or type_name == "void":
        return "void"
    elif type_name in ["int", "long", "float", "double", "boolean", "char", "byte", "short","int[]", "long[]", "float[]", "double[]", "boolean[]", "char[]", "byte[]", "short[]"]:
        return type_name
    else:
        # find the complete package + class name of the return type
        isArray = False
        if type_name.endswith("[]"):
            isArray = True
            type_name = type_name[:-2]
        type_mapping = type_module.TYPE_EXPANSION_MAP.get(type_name, type_name)
        
        if isinstance(type_mapping, list):
            print("Warning: type_mapping is a list")
        else:
            print("Warning: type_mapping is not a list")
        # if not found in the mapping, we return the original type name and print a warning
        if type_mapping == type_name:
            print(f" Warning: Type {type_name} not found in mapping. Using original type. ")
        if "<" in type_mapping:
            print(f" Warning: Type {type_name} contains 'Range'. This may indicate a generic type that is not properly handled. Using original type name. ")
        if isArray:
            type_mapping += "[]"
        return type_mapping
    return None

def refine_parameter_types(para_list: List[str]) -> List[str]:
    refined_params = []
    for para in para_list:
        refined_type = refine_type_name(para)
        if refined_type is None:
            print(f" Warning: Could not refine parameter type {para} ")
            continue
        refined_params.append(refined_type)
    return refined_params


def getMethodSignatureFromLabelledData(signature: str,class_name: str) -> str:
       # 1. Refine types FIRST to ensure the Method ID is valid
        return_type, method_name, para_list, para_names = helper.splitMethodSignatureFromJavaDoc(signature)
        return_type_clean = refine_type_name(return_type)
        if return_type_clean is None: 
            return None,None,None
        
        para_list_clean = refine_parameter_types(para_list)
        
        # 2. Reconstruct Method ID with CLEAN types
        clean_sig = f"{return_type_clean} {method_name}({','.join(para_list_clean)})"
        print(f" Clean method signature: {clean_sig} for class {class_name} ")
        method_id = f"{clean_sig}"
        return method_id,return_type_clean, para_list_clean

def generate_stubdroid_xml(json_data, output_dir,manual_directory="../data/javadoc/benchmark-dataflowspec/summariesManual"):

    # save the summaries for each item in the xml file, but for each class separately 
    # find all items for each class and save them in a separate xml file for that class, but here we save them all in one file and we keep track of the classes to avoid duplicates

    classes_list = {}  # to keep track of classes and avoid duplicates


    for item in json_data:
        class_name, raw_method_sig, category = item[1], item[2], item[3]

        if not classes_list.get(class_name, []):
            #print(f" Warning: Duplicate class name {class_name} found. Skipping this entry.")
            # add item in dictionary to keep track of duplicates and their counts
            classes_list[class_name] = []
        
        signature, returnTypeClean, paraListClean = getMethodSignatureFromLabelledData(raw_method_sig, class_name)
        if signature is None and returnTypeClean is None:
            print(f" Warning: Could not generate method signature for {raw_method_sig} in class {class_name}. Skipping this entry.")
            continue
        classes_list[class_name].append((signature, returnTypeClean, paraListClean, category))
    
    for class_name in classes_list:
        # for each class, we create a method element for each method signature and we add the flows for that method based on the category (source or sink)
            
        summary = ET.Element("summary", fileFormatVersion="103")

        # read the heading for class hierarchy from stubdroid xml file and add it to the summary
        # we can read it from any of the stubdroid xml files since they all have the same class hierarchy
        class_name_file = class_name + ".xml"
        manuall_xml_path = os.path.join(manual_directory, class_name_file)
        if os.path.exists(manuall_xml_path):
            tree = ET.parse(manuall_xml_path)
            root = tree.getroot()
            class_hierarchy_el = root.find("hierarchy")
            if class_hierarchy_el is not None:
                # We need to import the class hierarchy element from the original XML to avoid issues with namespaces or references

                summary.append(class_hierarchy_el)
        else:
            print(f" Warning: Stubdroid XML file for class {class_name} not found at {manuall_xml_path}. Skipping class hierarchy for this class.")

        methods_el = ET.SubElement(summary, "methods")

        for method_info in classes_list[class_name]:
            signature, returnTypeClean, para_list_clean, category = method_info
            method_id = f"{signature}"
            method_el = ET.SubElement(methods_el, "method", id=method_id)
            flows_el = ET.SubElement(method_el, "flows")

            # --- SOURCE LOGIC ---
            if "source" in category.lower():
                # Field -> Return (One flow is enough here)
                flow = ET.SubElement(flows_el, "flow", isAlias="false")
                ET.SubElement(flow, "from", {
                    "sourceSinkType": "Field",
                    "BaseType": class_name
                })
                ET.SubElement(flow, "to", {
                    "sourceSinkType": "Return",
                    "BaseType": returnTypeClean,
                    "taintSubFields": "true"
                })

            # --- SINK LOGIC ---
            if "sink" in category.lower():
                # Create a SEPARATE flow for each parameter
                for count, par_type in enumerate(para_list_clean):
                    flow = ET.SubElement(flows_el, "flow", isAlias="true")
                    
                    # Parameter -> Field
                    ET.SubElement(flow, "from", {
                        "sourceSinkType": "Parameter",
                        "ParameterIndex": str(count),
                        "BaseType": par_type
                    })
                    ET.SubElement(flow, "to", {
                        "sourceSinkType": "Field",
                        "BaseType": class_name,
                        "taintSubFields": "true"
                    })

        # 4. Pretty Print and Save
        xml_str = ET.tostring(summary, encoding='utf-8')
        pretty_xml = minidom.parseString(xml_str).toprettyxml(indent="    ")
        output_file = os.path.join(output_dir, f"{class_name}.xml")

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(pretty_xml)
    
        print(f"Summary successfully saved to {output_file}")

        # flush ET elements to free memory
        summary.clear()

if __name__ == "__main__":

    stubdroid_directory = '/home/maryam/clearblue/source-code/DAInfer/baseline/stubdroid/stubdroidSummary/'
    output_dir = '/home/maryam/clearblue/source-code/DAInfer/baseline/stubdroid/embeddingSummary/'
    manual_directory = '/home/maryam/clearblue/source-code/DAInfer/data/oracle/ManualOracle/labeledOracleDataflowSpecs.json'
    embedding_directory = '/home/maryam/clearblue/source-code/DAInfer/data/output/embedding-models/sentencebert-source-sink-3-5-mpnet/inferResult/benchmark_inferredSourceSinkSpecs.json'
    manual_summaries = []
    stubdroid_summaries = []
    stubdroid_classes = set()
    dainfer_summaries = []
    oracle_index = dict()   
    oracle_classes = set()

    # process xml summaries from stubdroid
    stubdroid_summaries, stubdroid_classes = process_xml_folder(stubdroid_directory)
    print(f"Processed {len(stubdroid_summaries)} stubdroid summaries for {len(stubdroid_classes)} classes.")

    # process xml summaries from manual summaries
    manual_summaries = load_specs_from_json(manual_directory)
    for o in manual_summaries:
        full_cls_name = o[0]
        if full_cls_name not in stubdroid_classes:
            continue
        cls_name = extract_simple_class_name(full_cls_name)
        return_type, method_name, para_list = splitMethodFromLabelledData(o[1])
        method = ""
        if para_list is None and method_name is not None and return_type is not None:
            method = f"{return_type} {method_name}()"
        elif para_list is not None and method_name is not None and return_type is not None:
            if len(para_list) >= 1:
                method = f"{return_type} {method_name}({','.join(para_list)})"
                print(f"Manual: Processing method {method}")  # Debug statement
            elif len(para_list) == 1:
                method = f"{return_type} {method_name}({para_list[0]})"
                print(f"Manual: Processing method {method}")  # Debug statement
            else:
                method = f"{return_type} {method_name}()"
        label = o[2]
        if method != "":
            method = method.lower()
            label = label.strip().lower()
            full_cls_name = full_cls_name.lower()
            key = (full_cls_name, method, label)
            oracle_index[key] = True
            print(f"Manual: Mapping loaded for oracle spec: {key} ")
        else:
            print(f"Manual: Skipped empty method for spec: {o} ")

    # read list of summaries from embedding models
    correct_embeddings = []
    wrong_embeddings = []
    embedding_summaries = load_specs_from_json(embedding_directory)
    for spec in embedding_summaries:
        full_cls_name = spec[1]
        if full_cls_name not in oracle_classes:
            oracle_classes.add(full_cls_name)
        if full_cls_name not in stubdroid_classes:
            continue
        cls_name = extract_simple_class_name(full_cls_name)
        print(f" spec2 : {spec[2]}  ")
        return_type, method_name, para_list,para_names = helper.splitMethodSignatureFromJavaDoc(spec[2])
        method = ""
        if para_list is None and method_name is not None and return_type is not None:
            print(f" method with no parameter : {method_name} ")
            method = f"{return_type} {method_name}()"
        elif para_list is not None and method_name is not None and return_type is not None:
            print(f" method with parameters : {method_name} with params {para_list} ")
            if len(para_list) > 1:
                method = f"{return_type} {method_name}({','.join(para_list)})"
                print(f"Embedding: Processing method {method}")  # Debug statement
            elif len(para_list) == 1:
                method = f"{return_type} {method_name}({para_list[0]})"
                print(f"Embedding: Processing method {method}")  # Debug statement
            else:
                method = f"{return_type} {method_name}()"
        label = spec[3]
        
        if method != "":
            print(f" method processed: {method} ")
            label = label.strip().lower()
            method = method.lower()
            full_cls_name = full_cls_name.lower()
            if label == "source-sink" or label == "sink-source":
                key1 = (full_cls_name, method, "source")
                key2 = (full_cls_name, method, "sink")
                if key1 in oracle_index and key2 in oracle_index:
                    correct_embeddings.append((full_cls_name, method, "source-sink"))
                else: 
                    if key1 in oracle_index:
                        correct_embeddings.append(key1)
                        wrong_embeddings.append(key2)
                        continue
                    if key2 in oracle_index:
                        correct_embeddings.append(key2)
                        wrong_embeddings.append(key1)
                        continue
                    print(f"Embedding: Missing SOURCE or SINK for: {full_cls_name}, {method} ")
                    wrong_embeddings.append((full_cls_name, method, "source-sink"))

            else:
                key = (full_cls_name, method, label)
                print(f"Embedding: Mapping loaded: {key} ")

                if key in oracle_index:
                    correct_embeddings.append(key)
                else:
                    print(f"Embedding: Wrong summary for oracle spec: {key} ")
                    wrong_embeddings.append(key)
        else:
            wrong_embeddings.append(spec)
            print(f"Embedding: Skipped empty method for spec: {spec} ")

    generate_stubdroid_xml(embedding_summaries, output_dir, manual_directory="../data/javadoc/benchmark-dataflowspec/summariesManual")
    # compare stubdroid vs. manual summaries
    correct_stubdroid = []
    wrong_stubdroid = []
    for spec in stubdroid_summaries:
        full_cls_name = spec[0]
        if full_cls_name not in stubdroid_classes:
            continue

        cls_name = extract_simple_class_name(full_cls_name)
        return_type, method_name, para_list = splitMethodFromLabelledData(spec[1])
        method = ""
        print(f" return type before {return_type}")
        if para_list is None and method_name is not None and return_type is not None:
            if "." in return_type:
                return_type = return_type.split(".")[-1]
            else:
                return_type = return_type
            method = f"{return_type} {method_name}()"
        elif para_list is not None and method_name is not None and return_type is not None:
            if "." in return_type:
                return_type = return_type.split(".")[-1]
            else:
                return_type = return_type
            if len(para_list) >= 1:
                method = f"{return_type} {method_name}({','.join(para_list)})"
                print(f"Stubdroid: Processing method {method}")  # Debug statement
            elif len(para_list) == 1:
                method = f"{return_type} {method_name}({para_list[0]})"
                print(f"Stubdroid: Processing method {method}")  # Debug statement
            else:
                method = f"{return_type} {method_name}()"
        print(f" return type after {return_type}")
        label = spec[2]
        if method != "":
            method = method.lower()
            label = label.strip().lower()
            full_cls_name = full_cls_name.lower()
            key = (full_cls_name, method, label)
            print(f"Stubdroid: Mapping loaded for: {key} ")

            if key in oracle_index:
                correct_stubdroid.append(key)
            else:
                print(f"Stubdroid: Wrong summary for: {key} ")
                wrong_stubdroid.append(key)
        else:
            wrong_stubdroid.append(spec)
            print(f"Stubdroid: Skipped empty method for spec: {spec} ")

    # compare embedding model vs. manual summaries
    print(f"Correct stubdroid summaries: {len(correct_stubdroid)}")
    print(f"Wrong stubdroid summaries: {len(wrong_stubdroid)}")
    print(f"Correct embedding model summaries: {len(correct_embeddings)}")
    print(f"Wrong embedding model summaries: {len(wrong_embeddings)}")
    print(f"Total oracle summaries: {len(oracle_index)}")
    print(f"Total oracle classes: {len(oracle_classes)}")
    print(f"Total stubdroid classes : {len(stubdroid_classes)}")
    print(f"Total stubdroid summaries: {len(stubdroid_summaries)}")
    print(f"Total embedding model summaries: {len(embedding_summaries)}")
    print(f" Precision and Recall for Stubdroid: Precision = {len(correct_stubdroid) / (len(correct_stubdroid) + len(wrong_stubdroid)):.2f}, Recall = {len(correct_stubdroid) / len(oracle_index):.2f}")
    print(f" Precision and Recall for Embedding Model: Precision = {len(correct_embeddings) / (len(correct_embeddings) + len(wrong_embeddings)):.2f}, Recall = {len(correct_embeddings) / len(oracle_index):.2f}")

    print(f"{len(oracle_classes - stubdroid_classes)} Number  Classes not in stubdroid but in oracle: {oracle_classes - stubdroid_classes}")
    # save all the files related to correct and wrong summaries
    open('/home/maryam/clearblue/source-code/DAInfer/baseline/stubdroid/stubdroid_correct_summaries.json', 'w', encoding='utf-8').write(json.dumps(correct_stubdroid, indent=4))
    open('/home/maryam/clearblue/source-code/DAInfer/baseline/stubdroid/stubdroid_wrong_summaries.json', 'w', encoding='utf-8').write(json.dumps(wrong_stubdroid, indent=4))
    open('/home/maryam/clearblue/source-code/DAInfer/baseline/stubdroid/embedding_correct_summaries.json', 'w', encoding='utf-8').write(json.dumps(correct_embeddings, indent=4))
    open('/home/maryam/clearblue/source-code/DAInfer/baseline/stubdroid/embedding_wrong_summaries.json', 'w', encoding='utf-8').write(json.dumps(wrong_embeddings, indent=4))   

    

    # compare stubdroid vs. embedding model summaries


    # Save the collected data to a JSON file
