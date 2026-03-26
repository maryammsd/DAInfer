prompt_modes = ["manualPrompt", "autoPrompt_FourTypes"]

gpt_modes = ["eager", "lazy"]

# For safety, we hide the OpenAI keys
# If you want to run DAInfer, please specify the keys
global_openai_key = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


# The parameters for self-consistency
global_n = 1  # Default value
global_m = 1  # Default value

# The temperature settings of the two-staged prompting
global_t1 = 0.7  # Default value
global_t2 = 0.7  # Default value

tagging_time = 0.0
solving_time = 0.0
tagTokenCnt = 0

# The parameter used for using LLM to infer alias or data flow specs. 
LLM = 'deepseek-v2:16b'
LLMTokenCnt = 0
LLMInputTokenCnt = 0
LLMOutputTokenCnt = 0
LLMTime = 0.0
promptMode = "dataflow_few" # dataflow_zero or dataflow_few
global_num_queries = {}
global_num_tokens = {}
global_num_descriptions_queried = {}
global_api_description_set = []
discarded_alias_queries = 0

# The parameters used when relying on the embedding model to infer alias or data flow specs.
EMBEDDING_MODEL = "sentencebert" # , e5, sentencebert
vector_dim = 384  # Default dimension for sentencebert all-MiniLM-L6-v2
memory_latency = 0.01  # in seconds
vector_shape = (1, vector_dim)
memory_usage_mb = 0.0015  # in MB
time_embedding_model = 0.0  # in seconds
count_embedding_model = 0   # number of times embedding model is called
EMBEDTime = 0.0
SENTENCEE_PROCESSING_TIME = 0.0
number_of_sentences = 0


OMTCnt = 0
SMTCnt = 0
