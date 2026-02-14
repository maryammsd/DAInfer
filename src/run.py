import sys
import copy
#from docParser import *
from gpt import *
from config import *
from difflib import SequenceMatcher
import spacy
import nltk
from omt import *
import concurrent.futures
import os
import json
import embedding
import datetime
from datetime import datetime


def obtainCHADic(methodDoc: dict):
    """
    Obtain the CHA dictionary from the methodDoc
    Args:
        methodDoc: The documentation model

    Returns:
        The CHA dictionary
    """
    CHADic = {}
    for package_name in methodDoc:
        for class_name in methodDoc[package_name]:
            #print(package_name)
            classInfo = methodDoc[package_name][class_name]
            #print(classInfo)
            CHADic[class_name] = classInfo["super class"]
    return CHADic


def constructFullMethodDic(methodDoc: dict, CHADic: dict):
    """
    Construct the full method dictionary
    Args:
        methodDoc: The documentation model
        CHADic: The CHA dictionary

    Returns:
        Flatten the documentation model
    """
    fullMethodDoc = {}
    for package_name in methodDoc:
        fullMethodDoc[package_name] = {}
        for class_name in methodDoc[package_name]:
            fullMethodDoc[package_name][class_name] = copy.deepcopy(
                methodDoc[package_name][class_name]
            )
            if class_name not in CHADic:
                continue
            for super_class in CHADic[class_name]:
                for package_name1 in methodDoc:
                    for class_name1 in methodDoc[package_name1]:
                        if super_class == class_name1:
                            fullMethodDoc[package_name][class_name]["methods"].update(
                                methodDoc[package_name1][class_name1]["methods"]
                            )
    return fullMethodDoc


def inferTypeConsistentSpecFromJavaDoc(
    methodDoc, CHADic, projectName, methodInfoResult_path
):
    """
    Infer type consistent specifications from JavaDoc
    Args:
        methodDoc: The documentation model
        CHADic: The class hierarchy dictionary
        projectName: The name of the project
        methodInfoResult_path: dump path
    """
    def isBlockedMethod(method: str):
        blockMethodNames = {"equals", "clone", "toString"}
        for s in blockMethodNames:
            if s in method:
                return True
        return False

    resultPath = methodInfoResult_path + projectName + "/"
    allTypeConsistentSpec = {}
    allCriticalMethods = {}
    cnt = 0
    method_cnt = 0

    for package_name in methodDoc:
        for className in methodDoc[package_name]:
            classInfo = methodDoc[package_name][className]
            methods = list(classInfo["methods"].keys())

            methodRetParaDic = {}
            for methodSig in methods:
                print(package_name, methodSig)
                retType, methodName, paraList, paraNames = (
                    splitMethodSignatureFromJavaDoc(methodSig)
                )
                if retType is None:
                    continue
                methodRetParaDic[methodSig] = {}
                methodRetParaDic[methodSig]["return type"] = retType
                methodRetParaDic[methodSig]["method name"] = methodName
                methodRetParaDic[methodSig]["parameters"] = paraList

            os.makedirs(resultPath + className, exist_ok=True)
            with open(resultPath + className + "/methodRetParaDic.json", "w") as f:
                json.dump(methodRetParaDic, f, indent=4)

            typeConsistentSpecs = set([])
            criticalMethods = set([])
            for sig1 in methodRetParaDic:
                if isBlockedMethod(sig1):
                    continue
                for sig2 in methodRetParaDic:
                    if isBlockedMethod(sig2):
                        continue
                    if sig1 == sig2:
                        continue
                    for k in range(len(methodRetParaDic[sig2]["parameters"])):
                        if isPrimitiveType(methodRetParaDic[sig2]["parameters"][k]):
                            continue
                        if (
                            getTypeSimilarity(
                                methodRetParaDic[sig2]["parameters"][k],
                                methodRetParaDic[sig1]["return type"],
                                CHADic,
                            )
                            != -1
                        ):
                            typeConsistentSpecs.add((sig2, sig1))
                            criticalMethods.add(sig1)
                            criticalMethods.add(sig2)
                            break
                    for k in range(len(methodRetParaDic[sig1]["parameters"])):
                        if isPrimitiveType(methodRetParaDic[sig1]["parameters"][k]):
                            continue
                        if (
                            getTypeSimilarity(
                                methodRetParaDic[sig1]["parameters"][k],
                                methodRetParaDic[sig2]["return type"],
                                CHADic,
                            )
                            != -1
                        ):
                            typeConsistentSpecs.add((sig1, sig2))
                            criticalMethods.add(sig1)
                            criticalMethods.add(sig2)
                            break

            typeConsistentSpecDic = {"typeConsistentSpecs": list(typeConsistentSpecs)}
            with open(resultPath + className + "/typeConsistentSpecs.json", "w") as f:
                json.dump(typeConsistentSpecDic, f, indent=4)
            if package_name not in allTypeConsistentSpec:
                allTypeConsistentSpec[package_name] = {}
            if package_name not in allCriticalMethods:
                allCriticalMethods[package_name] = {}
            allTypeConsistentSpec[package_name][className] = typeConsistentSpecs
            allCriticalMethods[package_name][className] = criticalMethods
            cnt += len(allTypeConsistentSpec[package_name][className])
            method_cnt += len(allCriticalMethods[package_name][className])
    return allTypeConsistentSpec, allCriticalMethods, cnt, method_cnt

### Added by Maryam - infer dataflow specs type with LLMs
def inferMemOpConsistentSpecWithLLM(
    preacceptedmethods: set, 
    methodDoc: dict,
    labeled_methods: dict,
    projectName: str,
    methodInfoResult_path: str
):
    resultPath = methodInfoResult_path + projectName + "/"
    memoryTypeFeature = {}
    acceptedSpecs = []
    

    cacheAllParameters = []
    history = set([])
    NThreads = 12

    print("Start LLM-based memory operation type inference... ")

    count_empty_desc = 0
    count_all_desc = 0

    for packageName in methodDoc:
        for className in methodDoc[packageName]:
            if className not in labeled_methods:
                continue
            for sig1 in methodDoc[packageName][className]["methods"].keys():
                print("Processing method:", sig1)
                if methodDoc[packageName][className]["methods"].get(sig1) is None:
                    continue
                if (packageName,className,sig1) not in preacceptedmethods:
                    continue

                isIn1 = False
                description1 = methodDoc[packageName][className]["methods"][sig1]
                if description1.strip() == "" :
                    continue
                if className in memoryTypeFeature:
                    if sig1 in memoryTypeFeature[className]:
                        isIn1 = True
                if not isIn1:
                    if className not in memoryTypeFeature:
                        memoryTypeFeature[className] = {}
                    if (
                        className,
                        sig1,
                        description1,
                    ) not in history:
                        history.add(
                            (
                                className,
                                sig1,
                                description1,
                            )
                        )
                        cacheAllParameters.append(
                            (
                                className,
                                sig1,
                                description1,
                                len(cacheAllParameters)
                            )
                        )
    def process_params(params):
        print("Processing parameters:", params)
        className, sig1, description, indx = params

        return (
            className,
            sig1,
            retrieve_dataflow_with_LLM(
                className, sig1, description, resultPath
            ),
        )

    # Create a thread pool executor with 5 threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=NThreads) as executor:
        # Submit tasks to the executor
        futures = [
            executor.submit(process_params, params) for params in cacheAllParameters
        ]

        # Retrieve results as they become available
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            className, sig1, memoryOperationType = result
            print("Obtained source-sink type:", sig1, "Data-flow type:", memoryOperationType)
            memoryTypeFeature[className][sig1] = memoryOperationType
            #responseLogs[(className, sig1)] = response

    for (packageName,className,sig1) in preacceptedmethods:
        if memoryTypeFeature.get(className) is None:
            continue
        if memoryTypeFeature[className].get(sig1) is None:
            continue            
        labels = memoryTypeFeature[className][sig1]
        for label in labels:
            if label != None and label.lower() != "none":
                acceptedSpecs.append(
                    [packageName, className, sig1, label]
                )

    print("Total methods with at least one empty description:", count_empty_desc, "out of", count_all_desc)

    return acceptedSpecs

### Added by Maryam - infer dataflow specs type with embedding models for each method independently
def inferMemOpConsistentSpecWithEmbeddingsSourceSink(
    preacceptedmethods: set, 
    methodDoc: dict,
    labeled_methods: dict,
    projectName: str,
    methodInfoResult_path: str,
    m,
    t2=1.0,
):  
    resultPath = methodInfoResult_path + projectName + "/"
    memoryTypeFeature = {}
    acceptedSpecs = []
    
    # Load the Sentence-BERT model
    model = embedding.run_embedding_models()
    if model is None:
        print("Embedding model not found!")
        print("Please check your configuration in config.py .")
        exit(0)

    
    history = set([])

    print("Start embedding-based memory operation type inference... ")

    count_empty_desc = 0
    count_all_desc = 0
    for packageName in methodDoc:
        for className in methodDoc[packageName]:
            if className not in labeled_methods:
                continue
            for sig1 in methodDoc[packageName][className]["methods"].keys():
                print("Processing method:", sig1)
                if methodDoc[packageName][className]["methods"].get(sig1) is None:
                    continue
                if (packageName,className,sig1) not in preacceptedmethods:
                    continue

                isIn1 = False
                description1 = methodDoc[packageName][className]["methods"][sig1]
                if description1.strip() == "" :
                    continue
                if className in memoryTypeFeature:
                    if sig1 in memoryTypeFeature[className]:
                        isIn1 = True
                if not isIn1:
                    if className not in memoryTypeFeature:
                        memoryTypeFeature[className] = {}
                    if (packageName,
                        className,
                        sig1,
                        description1,
                    ) not in history:
                        history.add(
                            (packageName,
                                className,
                                sig1,
                                description1,
                            )
                        )
                        
    
    embedding.initialize_targets(model)

    final_results, all_verbs = embedding.batch_retrieve_memory_operations(model, history)
    for result in final_results:
        for method_key in result:
            # Split method_key if needed
            packageName, className, sig1 = method_key
            print("Processing result for method:", sig1, "with description:", result[method_key])
            memoryOperationType = result[method_key]
            print("Obtained memory operation type for method:", sig1, "Type:", memoryOperationType)
            memoryTypeFeature[className][sig1] = memoryOperationType


    for (packageName,className,sig1) in preacceptedmethods:
        if memoryTypeFeature.get(className) is None:
            continue
        if memoryTypeFeature[className].get(sig1) is None:
            continue
        label = checkMemoryTypeEmbeddingSingleMethod(memoryTypeFeature[className][sig1])

        if not sig1.startswith("void"):
            if label == "sink":
                label = "sink-source"
            elif label == "none":
                label = "source"
        print(f"for method {sig1}, obtained label: {label} ")
        if label != "none":
            acceptedSpecs.append(
                [packageName, className, sig1, label]
            )

    for className in memoryTypeFeature: 
        os.makedirs(os.path.join(resultPath, className), exist_ok=True)
        with open(resultPath + className + "/dataflow_result_prompts.json", "a") as f:
            json.dump(memoryTypeFeature[className], f, indent=4)
    print("Total methods with at least one empty description:", count_empty_desc, "out of", count_all_desc)

    return acceptedSpecs

### Added by Maryam - infer memory type with Embeddings 
def inferMemOpConsistentSpecWithEmbeddings(
    preAcceptedSpecs, 
    methodDoc: dict,
    #allTypeConsistentSpec: dict,
    #allCriticalMethods: dict,
    CHADic: dict,
    projectName: str,
    methodInfoResult_path: str,
    m,
    t2=1.0,
):  
    resultPath = methodInfoResult_path + projectName + "/"
    memoryTypeFeature = {}
    acceptedSpecs = []
    # specify target operations 
    
    # Load the Sentence-BERT model
    model = embedding.load_sentencebert_model()

    
    cacheAllParameters = []
    history = set([])
    NThreads = 8

    print("Start embedding-based memory operation type inference... ")

    count_empty_desc = 0
    count_deprecated_desc = 0
    count_all_desc = 0

    for [packageName, className, sig1, sig2, opVal, conf, specStr] in preAcceptedSpecs:
        isIn1 = False
        isIn2 = False
        description1 = methodDoc[packageName][className]["methods"][sig1]
        description2 = methodDoc[packageName][className]["methods"][sig2]
        ## handle empty and depricated descriptions
        isEmpty1, isDeprecated1 = handleDescriptionCases(description1)
        isEmpty2, isDeprecated2 = handleDescriptionCases(description2)

        if isEmpty1 or isEmpty2:
            count_empty_desc += 1
            continue
        
        if isDeprecated1 or isDeprecated2:
            count_deprecated_desc += 1
            continue

        count_all_desc += 1
        if className in memoryTypeFeature:
            if sig1 in memoryTypeFeature[className]:
                isIn1 = True
            if sig2 in memoryTypeFeature[className]:
                isIn2 = True
        if not isIn1:
            if className not in memoryTypeFeature:
                memoryTypeFeature[className] = {}
            if (
                className,
                sig1,
                description1,
            ) not in history:
                history.add(
                    (
                        className,
                        sig1,
                        description1,
                    )
                )
                cacheAllParameters.append(
                    (
                        className,
                        sig1,
                        description1,
                        m,
                        t2,
                        len(cacheAllParameters)
                    )
                )
        if not isIn2:
            if className not in memoryTypeFeature:
                memoryTypeFeature[className] = {}
            if (
                className,
                sig2,
                methodDoc[packageName][className]["methods"][sig2],
            ) not in history:
                history.add(
                    (
                        className,
                        sig2,
                        description2,
                    )
                )
                cacheAllParameters.append(
                    (
                        className,
                        sig2,
                        description2,
                        m,
                        t2,
                        len(cacheAllParameters)
                    )
                )
    
    def process_params(params):
        print("Processing parameters:", params)
        className, sig1, description1, m, t2, indx = params

        return (
            className,
            sig1,
            retrieveMemoryOperationWithEmbeddings(
                model, className, sig1, description1, m, t2
            ),
        )

    # Create a thread pool executor with 5 threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=NThreads) as executor:
        # Submit tasks to the executor
        futures = [
            executor.submit(process_params, params) for params in cacheAllParameters
        ]

        # Retrieve results as they become available
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            className, sig1, memoryOperationType1 = result
            print("Obtained memory operation type for method:", sig1, "Type:", memoryOperationType1)
            memoryTypeFeature[className][sig1] = memoryOperationType1

    for [packageName, className, sig1, sig2, opVal, conf, specStr] in preAcceptedSpecs:
        if sig1 not in memoryTypeFeature.get(className, {}):
            print("Skipping method:", sig1, "as no memory type found.")
            continue
        if sig2 not in memoryTypeFeature.get(className, {}):
            print("Skipping method:", sig2, "as no memory type found.")
            continue
        print("Checking memory type consistency for methods:", sig1, sig2,checkMemoryTypeEmbedding(memoryTypeFeature[className][sig1],memoryTypeFeature[className][sig2]))
        if checkMemoryTypeEmbedding(
            memoryTypeFeature[className][sig1],
            memoryTypeFeature[className][sig2]
        ):
            acceptedSpecs.append(
                [packageName, className, sig1, sig2, opVal, conf, specStr]
            )

    for className in memoryTypeFeature:
        with open(resultPath + className + "/memoryTypeFeature_embedding_model.json", "w") as f:
            json.dump(memoryTypeFeature[className], f, indent=4)
    print("Total methods with at least one empty description:", count_empty_desc, "out of", count_all_desc)
    print("Total methods with at least one deprecated description:", count_deprecated_desc)

    return acceptedSpecs



def inferMemOpConsistentSpecInLazyMode(
    preAcceptedSpecs: list,
    methodDoc: dict,
    projectName: str,
    methodInfoResult_path,
    magicWords,
    promptMode,
    gptMode,
    m,
    t2=1.0,
):
    """
    Lazy strategy of neuro-symbolic optimization. Apply memory operation abstraction on demand.
    Args:
        preAcceptedSpecs: The specifications satisfying the other three constraints:
            - semantic unit consistency
            - validity constraint
            - degree constraint
        methodDoc: The documentation model
        projectName: the name of the project
        methodInfoResult_path: the dump path
        magicWords: The typical verbs as magic words
        promptMode: The mode of prompting
        gptMode: The mode of GPT
        m: The parameter of self-consistency
        t2: The temperature of the second stage of prompting

    Returns:
        The final inferred specifications
    """
    resultPath = methodInfoResult_path + projectName + "/"
    memoryTypeFeature = {}
    acceptedSpecs = []

    isValid = False
    for mode in prompt_modes:
        if mode in promptMode:
            isValid = True
            break
    if not isValid:
        print("wrong setting")
        exit(0)

    if gptMode != "non-cache":
        subdirs = [
            d
            for d in os.listdir(resultPath)
            if os.path.isdir(os.path.join(resultPath, d))
        ]
        for subdir in subdirs:
            singleResultPath = resultPath + subdir + "/"
            if os.path.exists(singleResultPath + "memoryTypeFeature.json"):
                print(singleResultPath + "memoryTypeFeature.json")
                with open(singleResultPath + "memoryTypeFeature.json", "r") as f:
                    memoryTypeFeature[subdir] = json.load(f)

    cacheAllParameters = []
    history = set([])
    NThreads = 8

    for [packageName, className, sig1, sig2, opVal, conf, specStr] in preAcceptedSpecs:
        isIn1 = False
        isIn2 = False
        if className in memoryTypeFeature:
            if sig1 in memoryTypeFeature[className]:
                isIn1 = True
            if sig2 in memoryTypeFeature[className]:
                isIn2 = True
        if not isIn1:
            if className not in memoryTypeFeature:
                memoryTypeFeature[className] = {}
            if (
                className,
                sig1,
                methodDoc[packageName][className]["methods"][sig1],
            ) not in history:
                history.add(
                    (
                        className,
                        sig1,
                        methodDoc[packageName][className]["methods"][sig1],
                    )
                )
                cacheAllParameters.append(
                    (
                        className,
                        sig1,
                        methodDoc[packageName][className]["methods"][sig1],
                        magicWords,
                        promptMode,
                        m,
                        t2,
                        len(cacheAllParameters),
                    )
                )
        if not isIn2:
            if className not in memoryTypeFeature:
                memoryTypeFeature[className] = {}
            if (
                className,
                sig2,
                methodDoc[packageName][className]["methods"][sig2],
            ) not in history:
                history.add(
                    (
                        className,
                        sig2,
                        methodDoc[packageName][className]["methods"][sig2],
                    )
                )
                cacheAllParameters.append(
                    (
                        className,
                        sig2,
                        methodDoc[packageName][className]["methods"][sig2],
                        magicWords,
                        promptMode,
                        m,
                        t2,
                        len(cacheAllParameters),
                    )
                )

    # Parallel version
    def process_params(params):
        className, sig1, description, magicWords, promptMode, m, t2, indx = params

        return (
            className,
            sig1,
            retrieveMemoryOperationType(
                className, sig1, description, magicWords, promptMode, m, t2
            ),
        )

    # Create a thread pool executor with 5 threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=NThreads) as executor:
        # Submit tasks to the executor
        futures = [
            executor.submit(process_params, params) for params in cacheAllParameters
        ]

        # Retrieve results as they become available
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            className, sig1, memoryOperationType = result
            memoryTypeFeature[className][sig1] = memoryOperationType
            print(len(cacheAllParameters))

    for [packageName, className, sig1, sig2, opVal, conf, specStr] in preAcceptedSpecs:
        if checkMemoryType(
            memoryTypeFeature[className][sig1],
            memoryTypeFeature[className][sig2],
            promptMode,
        ):
            acceptedSpecs.append(
                [packageName, className, sig1, sig2, opVal, conf, specStr]
            )

    for className in memoryTypeFeature:
        with open(resultPath + className + "/memoryTypeFeature.json", "w") as f:
            json.dump(memoryTypeFeature[className], f, indent=4)
    return acceptedSpecs


def inferMemOpConsistentSpecInEagerMode(
    methodDoc: dict,
    allTypeConsistentSpec: dict,
    allCriticalMethods: dict,
    CHADic: dict,
    projectName: str,
    methodInfoResult_path,
    magicWords,
    promptMode,
    gptMode,
    m,
    t2=1.0,
):
    """
    Eager strategy of neuro-symbolic optimization. Apply memory operation abstraction exhaustively.
    Args:
        methodDoc: The documentation model
        allTypeConsistentSpec: The specifications satisfying validity constraint and degree constraint
        allCriticalMethods: methods appering in the type consistent specifications
        CHADic: The class hierarchy dictionary
        projectName: The name of the project
        methodInfoResult_path: The dump path
        magicWords: The typical verbs as magic words
        promptMode: The mode of prompting
        gptMode: The mode of GPT
        m: The parameter of self-consistency
        t2: The temperature of the second stage of prompting

    Returns:
        The specifications satisfying validity constraint, degree constraint, and memory operation constraint
    """
    resultPath = methodInfoResult_path + projectName + "/"
    memoryTypeFeature = {}

    isValid = False
    for mode in prompt_modes:
        if mode in promptMode:
            isValid = True
            break
    if not isValid:
        print("wrong setting")
        exit(0)

    if gptMode != "non-cache":
        # Step 1(a): load the result from existing results
        subdirs = [
            d
            for d in os.listdir(resultPath)
            if os.path.isdir(os.path.join(resultPath, d))
        ]
        for subdir in subdirs:
            singleResultPath = resultPath + subdir + "/"
            # Open the JSON file for reading
            if os.path.exists(singleResultPath + "memoryTypeFeature.json"):
                print(singleResultPath + "memoryTypeFeature.json")
                with open(singleResultPath + "memoryTypeFeature.json", "r") as f:
                    memoryTypeFeature[subdir] = json.load(f)
    else:
        cacheAllParameters = []
        history = set([])
        NThreads = 8

        for package_name in methodDoc:
            for className in methodDoc[package_name]:
                if className not in allCriticalMethods:
                    continue
                criticalMethods = allCriticalMethods[package_name][className]
                memoryTypeFeature[className] = {}
                for methodSig in criticalMethods:
                    history.add(
                        (
                            className,
                            methodSig,
                            methodDoc[package_name][className]["methods"][methodSig],
                        )
                    )
                    cacheAllParameters.append(
                        (
                            className,
                            methodSig,
                            methodDoc[package_name][className]["methods"][methodSig],
                            magicWords,
                            promptMode,
                            m,
                            t2,
                            len(cacheAllParameters),
                        )
                    )

        def process_params(params):
            className, sig1, description, magicWords, promptMode, m, t2, indx = params
 
            return (
                className,
                sig1,
                retrieveMemoryOperationType(
                    className, sig1, description, magicWords, promptMode, m, t2
                ),
            )

        # Create a thread pool executor with 5 threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=NThreads) as executor:
            # Submit tasks to the executor
            futures = [
                executor.submit(process_params, params) for params in cacheAllParameters
            ]

            # Retrieve results as they become available
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                className, sig1, memoryOperationType = result
                memoryTypeFeature[className][sig1] = memoryOperationType
                print(len(cacheAllParameters))

        for package_name in methodDoc:
            for className in methodDoc[package_name]:
                if className not in allCriticalMethods:
                    continue
                os.makedirs(os.path.join(resultPath, className), exist_ok=True)
                with open(resultPath + className + "/memoryTypeFeature.json", "w") as f:
                    json.dump(memoryTypeFeature[className], f, indent=4)

    allMemOpConsistentSpec = {}
    cnt = 0
    for packageName in allTypeConsistentSpec:
        for className in allTypeConsistentSpec[packageName]:
            typeConsistentSpec = allTypeConsistentSpec[packageName][className]
            memOpConsistentSpec = []
            for spec in typeConsistentSpec:
                (sig1, sig2) = spec
                if className not in memoryTypeFeature:
                    memoryTypeFeature[className] = {}
                if sig1 not in memoryTypeFeature[className]:
                    isAnalyzed = False
                    if className in CHADic:
                        for superClass in CHADic[className]:
                            if superClass in memoryTypeFeature:
                                for tmpSig in memoryTypeFeature[superClass]:
                                    if tmpSig == sig1:
                                        memoryTypeFeature[className][sig1] = (
                                            memoryTypeFeature[superClass][tmpSig]
                                        )
                                        isAnalyzed = True
                                        break
                                if isAnalyzed:
                                    break
                    if not isAnalyzed:
                        memoryTypeFeature[className][sig1] = (
                            retrieveMemoryOperationType(
                                className,
                                sig1,
                                methodDoc[packageName][className]["methods"][sig1],
                                magicWords,
                                promptMode,
                                m,
                                t2,
                            )
                        )
                        continue
                if sig2 not in memoryTypeFeature[className]:
                    isAnalyzed = False
                    if className in CHADic:
                        for superClass in CHADic[className]:
                            if superClass in memoryTypeFeature:
                                for tmpSig in memoryTypeFeature[superClass]:
                                    if tmpSig == sig2:
                                        memoryTypeFeature[className][sig2] = (
                                            memoryTypeFeature[superClass][tmpSig]
                                        )
                                        isAnalyzed = True
                                        break
                                if isAnalyzed:
                                    break
                    if not isAnalyzed:
                        memoryTypeFeature[className][sig2] = (
                            retrieveMemoryOperationType(
                                className,
                                sig2,
                                methodDoc[packageName][className]["methods"][sig2],
                                magicWords,
                                promptMode,
                                m,
                                t2,
                            )
                        )
                        continue

                # Create the intermediate directories if they do not exist
                os.makedirs(os.path.join(resultPath, className), exist_ok=True)
                with open(resultPath + className + "/memoryTypeFeature.json", "w") as f:
                    json.dump(memoryTypeFeature[className], f, indent=4)

                if checkMemoryType(
                    memoryTypeFeature[className][sig1],
                    memoryTypeFeature[className][sig2],
                    promptMode,
                ):
                    memOpConsistentSpec.append(spec)
                    cnt += 1
            if packageName not in allMemOpConsistentSpec:
                allMemOpConsistentSpec[packageName] = {}
            allMemOpConsistentSpec[packageName][className] = memOpConsistentSpec
    return allMemOpConsistentSpec, memoryTypeFeature, cnt

def checkMemoryTypeEmbedding(memTypes1, memTypes2):
    check11 = ( memTypes1["insert"]) or (not memTypes1["remove"] and memTypes1["set"])
    check12 = memTypes2["get"] or memTypes2["remove"]
    return check11 and check12

    
def checkMemoryTypeEmbeddingSingleMethod(memTypes1):
    # before 
    #check11 = memTypes1["set"] or memTypes1["insert"] or memTypes1["remove"]
    #check12 = memTypes1["get"] or memTypes1["remove"]

    check11 = memTypes1["insert"] or (memTypes1["set"] and not memTypes1["remove"])
    check12 = memTypes1["get"] or memTypes1["remove"]
    if check11 and not check12:
        return "sink"
    elif check12 and not check11:
        return "source"
    elif check11 and check12:
        return "source-sink"
    return "none"

def checkMemoryType(memTypes1, memTypes2, promptMode):
    assert "manualPrompt" in promptMode or "autoPrompt_FourTypes" in promptMode
    check1 = memTypes1["insertion upon memory"] or (
        (not memTypes1["deletion upon memory"]) and memTypes1["memory write"]
    )
    check2 = memTypes2["memory read"]
    return check1 and check2


def constructSpecGraph(spec: list):
    [sig1, sig2] = spec
    retType1, methodName1, paraList1, paraNames1 = splitMethodSignatureFromJavaDoc(sig1)
    retType2, methodName2, paraList2, paraNames2 = splitMethodSignatureFromJavaDoc(sig2)

    nodeList1 = []
    nodeList2 = []
    nodeList1.append((retType1, methodName1))
    nodeList2.append((retType2, methodName2))

    for i in range(len(paraList1)):
        nodeList1.append((paraList1[i], paraNames1[i]))
    for i in range(len(paraList2)):
        nodeList2.append((paraList2[i], paraNames2[i]))
    return (nodeList1, nodeList2)


def computeSimilarityInSpecGraph(graph, CHADict: dict, NNSet: set):
    """
    Compute the similarity matrix
    """
    (nodeList1, nodeList2) = graph
    ftype = {}
    fname = {}
    for i in range(len(nodeList1)):
        for j in range(len(nodeList2)):
            (type1, name1) = nodeList1[i]
            (type2, name2) = nodeList2[j]
            ftype[(i, j)] = getTypeSimilarity(type1, type2, CHADict)
            fname[(i, j)] = computeNameSimilarity(name1, name2, NNSet, i == 0, j == 0)
    return ftype, fname


def inferRetArgSpecByOMTSolving(allMemoryValidSpecs: dict, NNSet: set, CHADic: dict):
    """
    Maximal matching
    """
    specs = {}
    print("Start OMT solving for memory valid specs")
    for packageName in allMemoryValidSpecs:
        for className in allMemoryValidSpecs[packageName]:
            for [sig1, sig2] in allMemoryValidSpecs[packageName][className]:
                graph = constructSpecGraph([sig1, sig2])
                ftype, fname = computeSimilarityInSpecGraph(graph, CHADic, NNSet)
                specStr, optVal = maximizeMatchingWeight_CHA(graph, ftype, fname, NNSet)
                print(f"{sig1} <-> {sig2} : {specStr} with optVal={optVal}")
                fieldConfidence = 1
                if specStr is not None and optVal is not None:
                    if packageName not in specs:
                        specs[packageName] = {}
                    if className not in specs[packageName]:
                        specs[packageName][className] = []
                    specs[packageName][className].append(
                        [sig1, sig2, optVal, fieldConfidence, specStr]
                    )
    return specs

def retrieveMethodsFromBaseline(fullMethodDoc: dict):
    methods = set()
    verb_dict = {}
    for package_name in fullMethodDoc:
        for className in fullMethodDoc[package_name]:
            info = fullMethodDoc[package_name][className]
            for sig in info["methods"]:
                description = info["methods"][sig]
                if description is not None and description.strip() != "":
                    methods.add(sig)
    return methods


def sortOMTSpec(specs: dict):
    flatenSpecs = []
    for packageName in specs:
        for className in specs[packageName]:
            for [sig1, sig2, opVal, fieldConfidence, specStr] in specs[packageName][
                className
            ]:
                flatenSpecs.append(
                    (
                        packageName,
                        className,
                        sig1,
                        sig2,
                        opVal,
                        fieldConfidence,
                        specStr,
                    )
                )
    flatenSpecs = sorted(flatenSpecs, key=lambda x: x[5])
    acceptSpecs = []

    for (
        packageName,
        className,
        sig1,
        sig2,
        opVal,
        fieldConfidence,
        specStr,
    ) in flatenSpecs:
        acceptSpecs.append(
            (packageName, className, sig1, sig2, opVal, fieldConfidence, specStr)
        )
    return flatenSpecs, acceptSpecs


def trimAcceptedSpecs(acceptedSpecs: list, CHADic: dict):
    finalizedSpecs = []
    for (
        packageName,
        className,
        sig1,
        sig2,
        opVal,
        fieldConfidence,
        specStr,
    ) in acceptedSpecs:
        superClasses = CHADic[className]
        isFinal = True
        for superClass in superClasses:
            for (
                packageNameTmp,
                classNameTmp,
                sigTmp1,
                sigTmp2,
                opValTmp,
                fieldConfidenceTmp,
                specStrTmp,
            ) in acceptedSpecs:
                if (
                    classNameTmp == superClass
                    and sig1 == sigTmp1
                    and sig2 == sigTmp2
                    and specStr == specStrTmp
                ):
                    isFinal = False
                    break
        if isFinal:
            finalizedSpecs.append(
                (packageName, className, sig1, sig2, opVal, fieldConfidence, specStr)
            )
    return finalizedSpecs


def trimAcceptedSpecsSourceSink(acceptedSpecs: list, CHADic: dict):
    finalizedSpecs = []
    for (
        packageName,
        className,
        sig1,
        label1
    ) in acceptedSpecs:
        superClasses = CHADic[className]
        isFinal = True
        for superClass in superClasses:
            for (
                packageNameTmp,
                classNameTmp,
                sigTmp1,
                label2
            ) in acceptedSpecs:
                if (
                    classNameTmp == superClass
                    and sig1 == sigTmp1
                ):
                    isFinal = False
                    break
        if isFinal:
            finalizedSpecs.append(
                (packageName, className, sig1, label1)
            )
    return finalizedSpecs



def extractNNDictionary(content_dict):
    NNSet = set([])
    wordtags = nltk.ConditionalFreqDist(
        (w.lower(), t) for w, t in nltk.corpus.brown.tagged_words(tagset="universal")
    )

    for package in content_dict:
        for className in content_dict[package]:
            info = content_dict[package][className]
            for sig in info["methods"]:
                description = sig[sig.find(" ") + 1 : sig.find("(")]
                ndes = re.sub(r"[^A-Za-z]+", "", description)
                # normalizeDes = re.findall('[A-Z][^A-Z]*', ndes[0:1].capitalize() + ndes[1:])
                normalizeDes = re.findall("[A-Z][^A-Z]*", ndes)
                sentences = nltk.sent_tokenize(" ".join(normalizeDes))
                for sent in sentences:
                    idx = 0
                    for word, tag in nltk.pos_tag(nltk.word_tokenize(sent)):
                        tags = dict(wordtags[word.lower()])
                        isNOUN = True
                        print(word, tags)
                        if "NOUN" in tags:
                            for tag in tags:
                                print(word, tag, tags[tag])
                                if tags[tag] > tags["NOUN"]:
                                    isNOUN = False
                        elif len(tags) != 0:
                            isNOUN = False
                        if isNOUN:
                            print(word.lower())
                            NNSet.add(word.lower())
    his = set([])
    for package in content_dict:
        for className in content_dict[package]:
            info = content_dict[package][className]
            for sig in info["methods"]:
                description = sig[sig.find(" ") + 1 : sig.find("(")]
                ndes = re.sub(r"[^A-Za-z]+", "", description)
                normalizeDes = re.findall(
                    "[A-Z][^A-Z]*", ndes[0:1].capitalize() + ndes[1:]
                )
                sentences = nltk.sent_tokenize(" ".join(normalizeDes))
                for sent in sentences:
                    for word, tag in nltk.pos_tag(nltk.word_tokenize(sent)):
                        if len(word) < 3:
                            continue
                        word = word.lower()
                        if word in NNSet or word in his:
                            continue
                        for nn in NNSet:
                            if word + "s" == nn or word + "es" == nn:
                                NNSet.add(word.lower())
                                break
                        his.add(word)
    for type in {
        "byte",
        "short",
        "int",
        "long",
        "float",
        "double",
        "char",
        "boolean",
        "void",
        "integer",
        "string",
    }:
        NNSet.add(type)
    return NNSet


def prepareBenchmark():
    evalSubjectJson = "../javadoc/evalSubject.json"
    evalDocDic = {}
    with open(evalSubjectJson, "r") as json_file:
        evalSubjects = json.load(json_file)
        for fullClassName in evalSubjects:
            filePath = evalSubjects[fullClassName][0]
            evalDocDic[fullClassName] = filePath

    methods = []
    methodDoc = {}
    for fullClassName in evalDocDic:
        filePath = evalDocDic[fullClassName]
        print(filePath)
        if os.path.exists("../data/javadoc/benchmark/" + fullClassName + ".json"):
            continue
        package_name, classInfo = pageParser(filePath, "")
        if package_name is not None and classInfo is not None:
            methods.append(classInfo)
            if package_name not in methodDoc:
                methodDoc[package_name] = {}
            methodDoc[package_name][classInfo["class"]] = classInfo
            with open("../data/javadoc/benchmark/" + fullClassName + ".json", "w") as f:
                json.dump(classInfo, f, indent=4)

    total_size = sum(len(lst) for lst in methodDoc.values())
    print(total_size, " classes obtained")
    return methodDoc


#### Added By Maryam
def computeSimilarityMatrixLLM(graph, CHADict: dict,className: str, sig1: str, sig2: str, desc1: str, desc2: str, promptMode: str):
    """
    Compute the similarity matrix
    """
    (nodeList1, nodeList2) = graph    
    result = retrieveAliasRelationwithLLM(className,sig1, sig2, desc1, desc2,promptMode)
    ftype = {}
    fname = {}
    for i in range(len(nodeList1)):
        for j in range(len(nodeList2)):
            (type1, name1) = nodeList1[i]
            (type2, name2) = nodeList2[j]
            ftype[(i, j)] = getTypeSimilarity(type1, type2, CHADict)
            if promptMode in ["alias_zero", "alias_few"]:
                fname[(i, j)] = getNameSimilarityFromLLM(name1, name2, result,i,j)
            else:
                fname[(i, j)] = getNameSimilarityScoreFromLLM(name1, name2, result)
    return ftype, fname


#### Added by Maryam
def getNameSimilarityFromLLM(name1: str, name2: str, result: dict, i: int, j: int):
    """
    Get name similarity from LLM result
    """
    for k, v in result.items():
        if v != "":
            if (k == name1 and v == name2) or (k == name2 and v == name1):
                return 1
        else:
            if(k == name1 and j == 0) or (k == name2 and i == 0):
                return 1
    return 0

#### Added by Maryam
def getNameSimilarityScoreFromLLM(name1: str, name2: str, result: dict):
    """
    Get name similarity from LLM result
    """
    for i,j , value in result:
        if (i == name1 and j == name2) or (i == name2 and j == name1):
            return value
    return 0


#### Added by Maryam to infer the alias relation using LLM and compute the similarity matrix based on the inferred alias relation
def inferAliasRelationWithLLM(methodDoc: dict, CHADic: dict, fullMethodDoc: dict   ):
    """
    Maximal matching
    """
    specs = {}
    promptmode = config.promptMode
    for packageName in methodDoc:
        for className in methodDoc[packageName]:
            for [sig1, sig2] in methodDoc[packageName][className]:
                graph = constructSpecGraph([sig1, sig2])
                ftype,fname = computeSimilarityMatrixLLM(graph, CHADic, className, sig1, sig2, fullMethodDoc[packageName][className]["methods"][sig1], fullMethodDoc[packageName][className]["methods"][sig2], promptmode
                )
                specStr, optVal = maximizeMatchingWeight_CHA_LLM(graph, ftype, fname)
                fieldConfidence = 1
                if specStr is not None and optVal is not None:
                    if packageName not in specs:
                        specs[packageName] = {}
                    if className not in specs[packageName]:
                        specs[packageName][className] = []
                    specs[packageName][className].append(
                        [sig1, sig2, optVal, fieldConfidence, specStr]
                    )
    return specs

def runBenchmark(promptMode, gptMode, n, m, isOptimizedMode=False, isLLM=False, t1=0.7, t2=0.7):
    """
    Run the benchmark
    Args:
        promptMode: The mode of prompting
        gptMode: The gpt mode. Non-cache would rerun the memory operation abstraction
        n: The self-consistency parameter in the first stage of prompting
        m: The self-consistency parameter in the second stage of prompting
        isOptimizedMode: whether the optimized mode (lazy or eager)
        t1: The temperature in the first stage of prompting
        t2: The temperature in the second stage of prompting
    """

    # Load Benchmark
    content_dict = {}
    dir_path = "../data/javadoc/benchmark/"
    data_path = "../data/output/alias-" + promptMode + "-" + config.EMBEDDING_MODEL + "/"
    if not os.path.exists(data_path):
        os.makedirs(data_path)

    inferResult_path = data_path + "inferResult/"
    if not os.path.exists(inferResult_path):
        os.makedirs(inferResult_path)

    methodInfoResult_path = data_path + "methodInfo/"
    if not os.path.exists(methodInfoResult_path):
        os.makedirs(methodInfoResult_path)
    if isLLM:
        prompt_path = data_path + "prompt/"
        if not os.path.exists(prompt_path):
            os.makedirs(prompt_path)

    # loop through each file in the directory
    for file_name in os.listdir(dir_path):
        # get the full file path
        file_path = os.path.join(dir_path, file_name)
        print(file_name)

        # check if the file is a JSON file
        if file_name.endswith(".json"):
            # open the file and load the JSON content to a dictionary
            fullClassName = file_name[0:-5]
            packageName = fullClassName
            className = fullClassName
            with open(file_path, "r") as f:
                content_dict[packageName] = {className: json.load(f)}

    ## Extract named entities
    if isOptimizedMode or not isLLM or not isEmbeddings:
        NNSet = extractNNDictionary(content_dict)
        with open(inferResult_path + "benchmark_NNSet.json", "w") as f:
            json.dump({"dic": list(NNSet)}, f, indent=4)

    ## Global CHA analysis
    CHADic = obtainCHADic(content_dict)

    with open(inferResult_path + "benchmark_CHADic.json", "w") as f:
        json.dump(CHADic, f, indent=4)

    fullMethodDoc = constructFullMethodDic(content_dict, CHADic)
    with open(inferResult_path + "benchmark_fullMethodDoc.json", "w") as f:
        json.dump(fullMethodDoc, f, indent=4)

    ## Type analysis
    if not isEmbeddingSourceSink:
        allTypeConsistentSpec, allCriticalMethods, cnt, method_cnt = (
            inferTypeConsistentSpecFromJavaDoc(
                fullMethodDoc, CHADic, "benchmark", methodInfoResult_path
            )
        )
        print("#allTypeConsistentSpec:", cnt)
        print("#Critical Methods:", method_cnt)

    ### There are five modes:
    ### 1. LLM + Dataflow  => handled separately
    ### 2. LLM + Alias
    ### 3. Non-optimized + LLM = lazy
    ### 4. Optimized + LLM = eager
    ### 5. Embedding models => handled separately

    completed = False
    
    ### 2. LLM-based alias relation inference
    if isLLM:
        classCnt = 0
        for package_name in fullMethodDoc:
            classCnt += len(fullMethodDoc[package_name])
        print(classCnt)
        retArgSpecs = {}
        retArgSpecs = inferAliasRelationWithLLM(allTypeConsistentSpec, CHADic, fullMethodDoc) 
            
        sortedRetArgSpecs, acceptedSpecs = sortOMTSpec(retArgSpecs)
        finalizedSpecs = trimAcceptedSpecs(acceptedSpecs, CHADic)
        completed = True

        # save the datat about tokens in a file
        with open(inferResult_path + "benchmark_LLM_token_usage.txt", "w") as f:
            f.write(f"Total LLM Tokens: {config.LLMTokenCnt}\n")
            f.write(f"#Total Queries: {sum(config.global_num_queries.values())}\n")
            f.write(f"#Dataflow Mode: {config.promptMode}\n")
            f.write(f"#Total Input vs. Output Tokens: {config.LLMInputTokenCnt} : {config.LLMOutputTokenCnt}\n")
            f.write(f"#Discarded Prompts {config.discarded_alias_queries}\n")
            sum = 0
            max = 0
            min = 1e9
            for key in config.global_num_queries:
                f.write(f"#Queries of {key}: {config.global_num_queries[key]}\n")
                if config.global_num_queries[key] > max:
                    max = config.global_num_queries[key]
                if min == 1e9 or config.global_num_queries[key] < min:
                    min = config.global_num_queries[key]
                sum += config.global_num_queries[key]
            f.write(f"#Max Queries: {max}\n")
            f.write(f"#Min Queries: {min}\n")
            f.write(f"#Sum Queries: {sum}\n")
            f.write(f"#Discarded Prompts: {config.discarded_alias_queries}\n")
            f.write(f"#Average Tokens per Query: {config.LLMTokenCnt / sum}\n")
            sum = 0
            for key in config.global_num_tokens:
                f.write(f"#Tokens of {key}: {config.global_num_tokens[key]}\n")
                sum += config.global_num_tokens[key]
            f.write(f"#Sum Tokens: {sum}\n")
        completed = True
    
        ### Embedding-based memory operation type inference
    
    if isEmbeddings and not completed:
        classCnt = 0
        for package_name in fullMethodDoc:
            classCnt += len(fullMethodDoc[package_name])
        print(classCnt)

        

        retArgSpecs = inferRetArgSpecByOMTSolving(allTypeConsistentSpec, NNSet, CHADic)

        sortedRetArgSpecs, preacceptedSpecs = sortOMTSpec(retArgSpecs)

        before = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        ## Embedding-based memory operation specifications
        acceptedSpecs = inferMemOpConsistentSpecWithEmbeddings(
            preacceptedSpecs,
            fullMethodDoc,
            #allTypeConsistentSpec,
            #allCriticalMethods,
            CHADic,
            "benchmark",
            methodInfoResult_path,
            m,
            t2,
        )
  

        finalizedSpecs = trimAcceptedSpecs(acceptedSpecs, CHADic)
        completed = True
        

        after_infer = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        duration = datetime.strptime(after_infer, "%Y-%m-%d_%H-%M-%S") - datetime.strptime(before, "%Y-%m-%d_%H-%M-%S")
         # Save time usage data in a file
        with open(inferResult_path + "benchmark_embedding_usage.txt", "w") as f:
            f.write(f"LLM Inference Start Time: {before}\n")
            f.write(f"LLM Inference End Time: {after_infer}\n")
            f.write(f"LLM Inference Duration: {duration}\n")
            f.write(f"Embedding models: {config.EMBEDDING_MODEL}\n")
            f.write(f"#Total memory latency: {config.memory_latency}\n")        
            f.write(f"#Total memory usage (MB): {config.memory_usage_mb}\n")
            f.write(f"#Total Time: {config.time_embedding_model}\n")
            f.write(f"#Total Embedding calls: {config.count_embedding_model}\n")


    if not isOptimizedMode and not completed:
        classCnt = 0
        for package_name in fullMethodDoc:
            classCnt += len(fullMethodDoc[package_name])
        print(classCnt)

        magicWords = retrieveMagicWords(promptMode, n, t1)
        with open(prompt_path + "magicWords.json", "w") as f:
            json.dump(magicWords, f, indent=4)

        allMemOpConsistentSpec, memoryFeature, memOpConsistentCnt = (
            inferMemOpConsistentSpecInEagerMode(
                fullMethodDoc,
                allTypeConsistentSpec,
                allCriticalMethods,
                CHADic,
                "benchmark",
                methodInfoResult_path,
                magicWords,
                promptMode,
                gptMode,
                m,
                t2,
            )
        )

        ## RetArg spec
        retArgSpecs = inferRetArgSpecByOMTSolving(allMemOpConsistentSpec, NNSet, CHADic)

        sortedRetArgSpecs, acceptedSpecs = sortOMTSpec(retArgSpecs)

        finalizedSpecs = trimAcceptedSpecs(acceptedSpecs, CHADic)
        completed = True
    elif not completed and isOptimizedMode:
        classCnt = 0
        for package_name in fullMethodDoc:
            classCnt += len(fullMethodDoc[package_name])
        print(classCnt)

        magicWords = retrieveMagicWords(promptMode, n, t1)
        with open(prompt_path + "magicWords.json", "w") as f:
            json.dump(magicWords, f, indent=4)

        # RetArg spec
        retArgSpecs = inferRetArgSpecByOMTSolving(allTypeConsistentSpec, NNSet, CHADic)

        sortedRetArgSpecs, preAcceptedSpecs = sortOMTSpec(retArgSpecs)

        acceptedSpecs = inferMemOpConsistentSpecInLazyMode(
            preAcceptedSpecs,
            fullMethodDoc,
            "benchmark",
            methodInfoResult_path,
            magicWords,
            promptMode,
            gptMode,
            m,
            t2,
        )

        print(config.LLMTokenCnt)

        print("\n")
        finalizedSpecs = trimAcceptedSpecs(acceptedSpecs, CHADic)
        completed = True

    if isLLM and completed:
        print(f"#Discarded Prompts {config.discarded_alias_queries}")
        sum = 0
        max = 0
        min = 1e9
        for key in config.global_num_queries:
            print(f"#Queries of {key}: {config.global_num_queries[key]}")
            if config.global_num_queries[key] > max:
                max = config.global_num_queries[key]
            if min == 1e9 or config.global_num_queries[key] < min:
                min = config.global_num_queries[key]
            sum += config.global_num_queries[key]
        print(f"#Max Queries: {max}")
        print(f"#Min Queries: {min}")
        print(f"#Sum Queries: {sum}")
        print(f"#Discarded Prompts: {config.discarded_alias_queries}")
        print(f"#Average Tokens per Query: {config.LLMTokenCnt / sum}")
        sum = 0
        for key in config.global_num_tokens:
            print(f"#Tokens of {key}: {config.global_num_tokens[key]}")
            sum += config.global_num_tokens[key]
        print(f"#Sum Tokens: {sum}")
        print(f"#Total LLM Tokens: {config.LLMTokenCnt}")

    if not isEmbeddingSourceSink:
        with open(inferResult_path + "benchmark_retArgSpecCandidate.json", "w") as f:
            json.dump({"retArgSpecCandidate": sortedRetArgSpecs}, f, indent=4)

        outlineDic = {}
        for spec in sortedRetArgSpecs:
            (package, className, sig1, sig2, opVal, fieldConf, specStr) = spec
            if className not in outlineDic:
                outlineDic[className] = []
            outlineDic[className].append([sig1, sig2, opVal, fieldConf, specStr])
        with open(inferResult_path + "benchmark_routlineDic.json", "w") as f:
            json.dump({"retArgSpecCandidate": outlineDic}, f, indent=4)

        with open(inferResult_path + "benchmark_inferredSpecs.json", "w") as f:
            json.dump({"retArgSpec": acceptedSpecs}, f, indent=4)

        with open(inferResult_path + "benchmark_finalizedSpecs.json", "w") as f:
            json.dump({"retArgSpec": finalizedSpecs}, f, indent=4)

        print("#typeConsistent:", cnt)
        print("#accepted specs: ", len(acceptedSpecs))
        print("#finalized specs: ", len(finalizedSpecs))
        print("#class: ", classCnt)
    else:
        with open(inferResult_path + "benchmark_inferredSourceSinkSpecs.json", "w") as f:
            json.dump({"sourceSinkSpec": acceptedSpecs}, f, indent=4)

        with open(inferResult_path + "benchmark_finalizedSourceSinkSpecs.json", "w") as f:
            json.dump({"sourceSinkSpec": finalizedSpecs}, f, indent=4)

        print("#accepted specs: ", len(acceptedSpecs))
        print("#finalized specs: ", len(finalizedSpecs))
        print("#class: ", classCnt)

def getLabelledMethodsForClass(labeled_methods: dict, className: str):
    method_list = []
    current_list = labeled_methods.get(className, [])
    for method_signature,label in current_list:
        init_string = method_signature.split(" ")
        if len(init_string) < 1:
            continue
        return_type_all = init_string[0]
        if "." in return_type_all:
            return_type = return_type_all.split(".")[-1]
        else:
            return_type = return_type_all
        rest_signature = " ".join(init_string[1:])
        method_signature = return_type + " " + rest_signature
        # keep only the type after the last dot in the method name
        method_list.append((method_signature, label))
    return method_list

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
    para_list = []
    if para_list_str.strip() != "":
        para_list_tmp = para_list_str.split(",")
        for para in para_list_tmp:
            para = para.strip()
            if "." in para:
                para_type = para.split(".")[-1]
            else:
                para_type = para
            para_list.append(para_type)
    if return_type == "T":
        return_type = "Object"
    return return_type, method_name, para_list


def exists_signature_in_list(signature: str, signature_list: list):
    return_type1, methodName1, paraList1, paraNames = splitMethodSignatureFromJavaDoc(signature)
    count = 0
    matches = []
    for sig,label in signature_list:
        return_type2, methodName2, paraList2 = splitMethodFromLabelledData(sig)
        if return_type1 is None or return_type2 is None:
            continue
        if return_type1.lower() != return_type2.lower():
            continue
        if methodName1.lower() != methodName2.lower():
            continue
        if len(paraList1) != len(paraList2):
            continue
        match = True
        for i in range(len(paraList1)):
            if paraList1[i].lower() != paraList2[i].lower():
                match = False
                break
        if match:
            count += 1
            matches.append((sig, label))
    if len(matches) > 0:
        return True, count
    return False,count

### Added by Maryam to run the benchmark for source-sink detection using LLM-based prompting
def runBenchmarkDataflowSourceSinkLLM(mode, n, m, LLMModel,promptMode):
    """
    Run the benchmark
    Args:
        mode: The mode of source-sink detection
        n: The self-consistency parameter in the first stage of prompting
        m: The self-consistency parameter in the second stage of prompting
    """

    # Load Benchmark
    content_dict = {}
    dir_path = "../data/javadoc/benchmark-dainfer+/"
    data_path = "../data/output/LLM-"+ LLMModel + "-" + mode + "-source-sink-" + str(m) + "-" + str(n) + "/"
    labeled_classes_path = "../data/oracle/ManualOracle/labeledClassesDataflow.json"
    labeled_methods_path = "../data/oracle/ManualOracle/labeledOracleDataflowSpecs.json"
    if not os.path.exists(data_path):
        os.makedirs(data_path)
    
    # retrieve labeled classes list
    if not os.path.exists(labeled_classes_path):
        print("[Error] Labeled classes file not found!")
        return
    labeled_classes = []
    with open(labeled_classes_path, "r") as f:
        labeled_classes_content = json.load(f)
        # get all classes names under the "labeledClasses" key
        if "labeledClasses" in labeled_classes_content:
            labeled_classes_content = labeled_classes_content["labeledClasses"]
            for class_name in labeled_classes_content:
                labeled_classes.append(class_name)
        else:
            print("[Error] No labeled classes found!")
            return
    
    # retrieve labeled methods list
    if not os.path.exists(labeled_methods_path):
        print("[Error] Labeled methods file not found!")
        return
    labeled_methods = {}
    method_count = 0
    with open(labeled_methods_path, "r") as f:
        labeled_methods_content = json.load(f)
        # get all the ones in [] 
        # the data format is like this: [  [class_name1, method_signature1, label1], [class_name2, method_signature2, label2] ,  ...   ],
        for item in labeled_methods_content:
            class_name = item[0]
            method_signature = item[1]
            #print("Labeled Method Item:", item)
            label = item[2]
            if class_name not in labeled_methods:
                labeled_methods[class_name] = []
            labeled_methods[class_name].append((method_signature,label))
        for class_name in labeled_methods:
            print("--------------------------------------------------")
            print(f"Labeled Class {class_name} has {len(labeled_methods[class_name])} labeled methods.")
            for method_signature, label in labeled_methods[class_name]:
                print(f"  Labeled Method: {method_signature} with label {label}")


    # Create output directories
    inferResult_path = data_path + "inferResult/"
    if not os.path.exists(inferResult_path):
        os.makedirs(inferResult_path)

    methodInfoResult_path = data_path + "methodInfo/"
    if not os.path.exists(methodInfoResult_path):
        os.makedirs(methodInfoResult_path)
    methodPrompt_path = data_path + "methodPrompt/"
    if not os.path.exists(methodPrompt_path):
        os.makedirs(methodPrompt_path)
    

    skipped_classes = 0
    all_classes = 0

    # loop through each file in the directory
    for file_name in os.listdir(dir_path):
        # get the full file path
        file_path = os.path.join(dir_path, file_name)
        all_classes += 1

        # check if the file is a JSON file
        if file_name.endswith(".json"):
            fullClassName = file_name[0:-5]
            if fullClassName not in labeled_classes:
                skipped_classes += 1
                #print("Skipping unlabeled class:", fullClassName)
                continue
            #print(f"Found Class File for {fullClassName} ")
            # open the file and load the JSON content to a dictionary
            packageName = fullClassName
            className = fullClassName
            with open(file_path, "r") as f:
                content_dict[packageName] = {className: json.load(f)}



    ## Global CHA analysis
    CHADic = obtainCHADic(content_dict)

    with open(inferResult_path + "benchmark_CHADic.json", "w") as f:
        json.dump(CHADic, f, indent=4)

    fullMethodDoc = constructFullMethodDic(content_dict, CHADic)
    with open(inferResult_path + "benchmark_fullMethodDoc.json", "w") as f:
        json.dump(fullMethodDoc, f, indent=4)

    
    count_desc = 0
    count_all_desc = 0
    count_all_existing_methods = 0
    count_deprecated = 0    
    count_specs = 0
    print("Total labeled classes to process:", len(labeled_classes))
    print("Let's see how many we can read with descriptions ... ")
    preacceptedmethods = set()
    for package_name in fullMethodDoc:
        print("------------------------------------------------------------------")
        for className in fullMethodDoc[package_name]:
            method_for_class = getLabelledMethodsForClass(labeled_methods, className) #labeled_methods.get(className, [])
            if len(method_for_class) == 0:
                continue
            info = fullMethodDoc[package_name][className]
            collected_methods = 0
            for sig in info["methods"]:
                exist_is, count = exists_signature_in_list(sig, method_for_class)
                if exist_is is False:
                #if sig not in method_for_class:
                #if not findMethodInLabelledMethods(labeled_methods, className, sig):
                    #print("Skipping unlabeled method:", sig, " in class ", className)
                    continue
                method_count += 1
                if not (package_name,className,sig) in preacceptedmethods:
                    count_all_existing_methods += 1
                    count_all_desc += 1
                description = info["methods"][sig]
                #print("Processing labeled method:", sig, " in class ", className, " with description ",description)
                isEmpty, isDeprecated = handleDescriptionCases(description)
                if not isEmpty and not isDeprecated:
                    count_specs += count
                    if (package_name,className,sig) in preacceptedmethods:
                        print("Already pre-accepted method:", sig, " in class ", className)
                    else:
                        count_desc += 1
                        preacceptedmethods.add((package_name, className, sig))
                        collected_methods += 1
                elif not isEmpty and isDeprecated:
                    count_deprecated += 1
                else:
                    print("No description found for labeled method:", sig, " in class ", className)
        if collected_methods != len(method_for_class):
            print(f"Processing Class: {className} with {len(method_for_class)} labeled methods and {len(info['methods'])} documented methods.")
            print("Collected methods so far for class:", className, " are ", collected_methods)

    print("Total labeled classes:", len(labeled_classes))
    print("Total classes processed:", len(content_dict))
    print("Total classes skipped:", skipped_classes)
    print("Total classes under benchmark path:", all_classes)
    print("Total labeled for methods:", method_count)
    print("Total labeled specs with descriptions:", count_specs)
    print("Total existing labeled methods in the documentation:", count_all_existing_methods)
    print("Total labeled methods with descriptions:", count_desc)
    print("Total labeled methods with deprecated descriptions:", count_deprecated)
    print("Description coverage:", count_desc, "/", count_all_desc)
    acceptedSpecs = {}
    before = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    acceptedSpecs = inferMemOpConsistentSpecWithLLM(
        preacceptedmethods,
        fullMethodDoc,
        labeled_methods,
        "benchmark-llm-method",
        methodInfoResult_path
    )

    after_infer = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    duration = datetime.strptime(after_infer, "%Y-%m-%d_%H-%M-%S") - datetime.strptime(before, "%Y-%m-%d_%H-%M-%S")
    finalizedSpecs = trimAcceptedSpecsSourceSink(acceptedSpecs, CHADic)
    
    # Save LLM and time usage data in a file
    with open(inferResult_path + "benchmark_LLM_token_usage.txt", "w") as f:
        f.write(f"LLM Inference Start Time: {before}\n")
        f.write(f"LLM Inference End Time: {after_infer}\n")
        f.write(f"LLM Inference Duration: {duration}\n")
        f.write(f"Total LLM Tokens: {config.LLMTokenCnt}\n")
        ###f.write(f"#Total Queries: {sum(config.global_num_queries.values())}\n")
        f.write(f"#Dataflow Mode: {config.promptMode}\n")
        f.write(f"#Total Input vs. Output Tokens: {config.LLMInputTokenCnt} : {config.LLMOutputTokenCnt}\n")
        f.write(f"#Discarded Prompts {config.discarded_alias_queries}\n")
        sum = 0
        max = 0
        min = 1e9
        for key in config.global_num_queries:
            f.write(f"#Queries of {key}: {config.global_num_queries[key]}\n")
            if config.global_num_queries[key] > max:
                max = config.global_num_queries[key]
            if min == 1e9 or config.global_num_queries[key] < min:
                min = config.global_num_queries[key]
            sum += config.global_num_queries[key]
        f.write(f"#Max Queries: {max}\n")
        f.write(f"#Min Queries: {min}\n")
        f.write(f"#Sum Queries: {sum}\n")
        f.write(f"#Average Tokens per Query: {config.LLMTokenCnt / sum}\n")
        sum = 0
        for key in config.global_num_tokens:
            f.write(f"#Tokens of {key}: {config.global_num_tokens[key]}\n")
            sum += config.global_num_tokens[key]
        f.write(f"#Sum Tokens: {sum}\n")

    # Save results and print the statistics
    with open(inferResult_path + "benchmark_inferredDataflowSpec.json", "w") as f:
        json.dump({"dataflowSpec": acceptedSpecs}, f, indent=4)

    with open(inferResult_path + "benchmark_finalizedDataflowSpecs.json", "w") as f:
        json.dump({"dataflowSpec": finalizedSpecs}, f, indent=4)

    print("#accepted specs: ", len(acceptedSpecs))
    print("#finalized specs: ", len(finalizedSpecs))

### Added by Maryam to handle the cases of descriptions in the benchmark, such as empty description, deprecated description, etc.
def handleDescriptionCases(description: str):
    isEmpty = False
    isDeprecated = False
    if description is None:
        isEmpty = True
        return isEmpty, isDeprecated
    desc = description.strip()
    if desc == "":
        isEmpty = True
    # replace new line characters with space
    desc = desc.replace("\n", " ")
    desc = desc.replace("\r", " ")
    # replace multiple spaces with single space
    desc = re.sub(' +', ' ', desc)
    if "deprecated" in desc.lower():
        isDeprecated = True

    return isEmpty, isDeprecated

### Added by Maryam to run the benchmark for source-sink detection using embedding-based prompting
def runBenchmarkDataflowSourceSinkEmbedding(mode, n, m):
    """
    Run the benchmark
    Args:
        mode: The mode of source-sink detection
        n: The self-consistency parameter in the first stage of prompting
        m: The self-consistency parameter in the second stage of prompting
    """

    # Load Benchmark
    content_dict = {}
    dir_path = "../data/javadoc/benchmark-dainfer+/"
    data_path = "../data/output/" + config.EMBEDDING_MODEL + "-source-sink-" + str(m) + "-" + str(n) + "/"
    labeled_classes_path = "../data/oracle/ManualOracle/labeledClassesDataflow.json"
    labeled_methods_path = "../data/oracle/ManualOracle/labeledOracleDataflowSpecs.json"
    if not os.path.exists(data_path):
        os.makedirs(data_path)
    
    # retrieve labeled classes list
    if not os.path.exists(labeled_classes_path):
        print("[Error] Labeled classes file not found!")
        return
    labeled_classes = []
    with open(labeled_classes_path, "r") as f:
        labeled_classes_content = json.load(f)
        # get all classes names under the "labeledClasses" key
        if "labeledClasses" in labeled_classes_content:
            labeled_classes_content = labeled_classes_content["labeledClasses"]
            for class_name in labeled_classes_content:
                labeled_classes.append(class_name)
        else:
            print("[Error] No labeled classes found!")
            return
    
    # retrieve labeled methods list
    if not os.path.exists(labeled_methods_path):
        print("[Error] Labeled methods file not found!")
        return
    
    labeled_methods = {}

    method_count = 0
    with open(labeled_methods_path, "r") as f:
        labeled_methods_content = json.load(f)
        # get all the ones in [] 
        # the data format is like this: [  [class_name1, method_signature1, label1], [class_name2, method_signature2, label2] ,  ...   ],
        for item in labeled_methods_content:
            class_name = item[0]
            method_signature = item[1]
            #print("Labeled Method Item:", item)
            label = item[2]
            if class_name not in labeled_methods:
                labeled_methods[class_name] = []
            labeled_methods[class_name].append((method_signature,label))
            method_count += 1
        for class_name in labeled_methods:
            print("--------------------------------------------------")
            print(f"Labeled Class {class_name} has {len(labeled_methods[class_name])} labeled methods.")
            for method_signature, label in labeled_methods[class_name]:
                print(f"  Labeled Method: {method_signature} with label {label}")

    # Create output directories
    inferResult_path = data_path + "inferResult/"
    if not os.path.exists(inferResult_path):
        os.makedirs(inferResult_path)

    methodInfoResult_path = data_path + "methodInfo/"
    if not os.path.exists(methodInfoResult_path):
        os.makedirs(methodInfoResult_path)

    skipped_classes = 0
    all_classes = 0
    # loop through each file in the directory
    for file_name in os.listdir(dir_path):
        # get the full file path
        file_path = os.path.join(dir_path, file_name)
        all_classes += 1

        # check if the file is a JSON file
        if file_name.endswith(".json"):
            fullClassName = file_name[0:-5]
            if fullClassName not in labeled_classes:
                skipped_classes += 1
                #print("Skipping unlabeled class:", fullClassName)
                continue
            #print(f"Found Class File for {fullClassName} ")
            # open the file and load the JSON content to a dictionary
            packageName = fullClassName
            className = fullClassName
            with open(file_path, "r") as f:
                content_dict[packageName] = {className: json.load(f)}



    ## Global CHA analysis
    CHADic = obtainCHADic(content_dict)

    with open(inferResult_path + "benchmark_CHADic.json", "w") as f:
        json.dump(CHADic, f, indent=4)

    fullMethodDoc = constructFullMethodDic(content_dict, CHADic)
    with open(inferResult_path + "benchmark_fullMethodDoc.json", "w") as f:
        json.dump(fullMethodDoc, f, indent=4)

    
    count_desc = 0
    count_all_desc = 0
    count_all_existing_methods = 0
    count_deprecated = 0    
    count_specs = 0
    verb_dict = {}

    print("Total labeled classes to process:", len(labeled_classes))
    print("Let's see how many we can read with descriptions ... ")
    preacceptedmethods = set()
    for package_name in fullMethodDoc:
        print("------------------------------------------------------------------")
        for className in fullMethodDoc[package_name]:
            method_for_class = getLabelledMethodsForClass(labeled_methods, className) #labeled_methods.get(className, [])
            if len(method_for_class) == 0:
                continue
            info = fullMethodDoc[package_name][className]
            collected_methods = 0
            for sig in info["methods"]:
                exist_is, count = exists_signature_in_list(sig, method_for_class)
                if exist_is is False:
                #if sig not in method_for_class:
                #if not findMethodInLabelledMethods(labeled_methods, className, sig):
                    print("Skipping unlabeled method:", sig, " in class ", className)
                    continue
                if not (package_name,className,sig) in preacceptedmethods:
                    count_all_existing_methods += 1
                    count_all_desc += 1
                description = info["methods"][sig]
                isEmpty, isDeprecated = handleDescriptionCases(description)
                if not isEmpty and not isDeprecated:
                    count_specs += count
                    if (package_name,className,sig) in preacceptedmethods:
                        print("Already pre-accepted method:", sig, " in class ", className)
                    else:
                        count_desc += 1
                        preacceptedmethods.add((package_name, className, sig))
                        collected_methods += 1
                elif not isEmpty and isDeprecated:
                    count_deprecated += 1
                else:
                    print("No description found for labeled method:", sig, " in class ", className)
        if collected_methods != len(method_for_class):
            print(f"Processing Class: {className} with {len(method_for_class)} labeled methods and {len(info['methods'])} documented methods.")
            print("Collected methods so far for class:", className, " are ", collected_methods)


    print("Total labeled classes:", len(labeled_classes))
    print("Total classes processed:", len(content_dict))
    print("Total classes skipped:", skipped_classes)
    print("Total classes under benchmark path:", all_classes)
    print("Total labeled for methods:", method_count)
    print("Total labeled specs with descriptions:", count_desc)
    print("Total existing labeled methods in the documentation:", count_all_existing_methods)
    print("Description coverage:", count_desc, "/", count_all_desc)
    print("Deprecated methods:", count_deprecated)
    
    before = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    acceptedSpecs = inferMemOpConsistentSpecWithEmbeddingsSourceSink(
        preacceptedmethods,
        fullMethodDoc,
        labeled_methods,
        "benchmark-single-method",
        methodInfoResult_path,
        m,
        t2,
    )
     
    after_infer = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    duration = datetime.strptime(after_infer, "%Y-%m-%d_%H-%M-%S") - datetime.strptime(before, "%Y-%m-%d_%H-%M-%S")
  

    finalizedSpecs = trimAcceptedSpecsSourceSink(acceptedSpecs, CHADic)
    

    # Save results and print the statistics
    with open(inferResult_path + "benchmark_inferredSourceSinkSpecs.json", "w") as f:
        json.dump({"sourceSinkSpec": acceptedSpecs}, f, indent=4)

    with open(inferResult_path + "benchmark_finalizedSourceSinkSpecs.json", "w") as f:
        json.dump({"sourceSinkSpec": finalizedSpecs}, f, indent=4)

        
    # Save time usage data in a file
    with open(inferResult_path + "benchmark_embedding_usage.txt", "w") as f:
        f.write(f"Embedding Inference Start Time: {before}\n")
        f.write(f"Embedding Inference End Time: {after_infer}\n")
        f.write(f"Embedding Inference Duration: {duration}\n")
        f.write(f"Embedding analysis time {config.EMBEDTime}")
        f.write(f"Embedding models: {config.EMBEDDING_MODEL}\n")
        f.write(f"#Total memory latency: {config.memory_latency}\n")        
        f.write(f"#Total memory usage (MB): {config.memory_usage_mb}\n")
        f.write(f"#Total Time: {config.time_embedding_model}\n")
        f.write(f"#Total Embedding calls: {config.count_embedding_model}\n")

    print("#accepted specs: ", len(acceptedSpecs))
    print("#finalized specs: ", len(finalizedSpecs))

def construct():
    directory = "../data/javadoc/benchmark-dainfer+/"  # Specify the directory name

    # Get all the files in the directory
    files = os.listdir(directory)

    # Filter JSON files
    json_files = [file for file in files if file.endswith(".json")]

    # Print the list of JSON files
    jsonContent = {}
    for className in json_files:
        jsonContent[className.replace(".json", "")] = className.replace(".json", "")
        print('"' + className.replace(".json", "") + '",')

    with open("../data/javadoc/evalSubject.json", "w") as f:
        json.dump(jsonContent, f, indent=4)
    return jsonContent


if __name__ == "__main__":
    assert len(sys.argv) == 6

    config.key_id = 0
    m = int(sys.argv[1])
    n = int(sys.argv[2])
    t1 = float(sys.argv[3])
    t2 = float(sys.argv[4])

    isOptimizedMode = False
    isLLM = False
    check_verbs = False
    isDataflow = False
    isEmbeddings = False
    isEmbeddingSourceSink = False
    if sys.argv[5] == "--lazy":
        isOptimizedMode = True
    elif sys.argv[5] == "--eager":
        isOptimizedMode = False
    elif sys.argv[5] == "--llm":
        isLLM = True
    elif sys.argv[5] == "--llm-dataflow":
        isLLM = True
        isDataflow = True
        # promptMode can be 1) dataflow_zero 2) dataflow_few
        promptMode = config.promptMode
        runBenchmarkDataflowSourceSinkLLM("non-cache", n, m,config.LLM,  promptMode=promptMode)
        exit(0)
    elif sys.argv[5] == "--embed":
        isEmbeddings = True
    elif sys.argv[5] == "--sink-source":
        isEmbeddingSourceSink = True
        print("=========================================")
        print("Running Source-Sink Embedding Model...")
        runBenchmarkDataflowSourceSinkEmbedding("non-cache", m, n)
        exit(0)
    else:
        print("Wrong Argument!")
        exit(0)


    (config.global_m, config.global_n, config.global_t1, config.global_t2) = (m, n, t1, t2)

    promptMode = (
        "llm_autoPrompt_FourTypes_" + str(m) + "_" + str(n) + "_" + str(t1) + "_" + str(t2)
    )
    runBenchmark(promptMode, "non-cache", m, n, isOptimizedMode, isLLM, t1, t2)
    exit(0)
