# fmt: off
import logging

from farm.data_handler.data_silo import DataSilo
from farm.data_handler.processor import NERProcessor
from farm.modeling.optimization import initialize_optimizer
from farm.infer import Inferencer
from farm.modeling.adaptive_model import AdaptiveModel
from farm.modeling.language_model import LanguageModel
from farm.modeling.prediction_head import TokenClassificationHead
from farm.modeling.tokenization import Tokenizer
from farm.train import Trainer
from farm.utils import set_all_seeds, MLFlowLogger, initialize_device_settings
from pathlib import Path
home = str(Path.home())
data_path = home+'/data/germEval_2014'

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s -   %(message)s",
    datefmt="%m/%d/%Y %H:%M:%S",
    level=logging.INFO,
)

ml_logger = MLFlowLogger('mlruns')
ml_logger.init_experiment(experiment_name="GermEval-2014-NER", run_name="3 epochs, multilingual-bert; seed 123")

##########################
########## Settings
##########################
set_all_seeds(seed=123)
device, n_gpu = initialize_device_settings(use_cuda=True)
n_epochs = 3
batch_size = 16
evaluate_every = 100
lang_model = "bert-base-multilingual-cased"

# 1.Create a tokenizer
tokenizer = Tokenizer.load(
    pretrained_model_name_or_path=lang_model,
    do_lower_case=False)

# 2. Create a DataProcessor that handles all the conversion from raw text into a pytorch Dataset
# ner_labels = ["[PAD]", "X", "O", "B-MISC", "I-MISC", "B-PER", "I-PER", "B-ORG", "I-ORG", "B-LOC", "I-LOC", "B-OTH", "I-OTH"]
with open(data_path+'/labels.txt','r') as f:
    ner_labels = [l.replace('\n','') for l in f.readlines()]+['X',"[PAD]"]

processor = NERProcessor(
    tokenizer=tokenizer, max_seq_len=128, data_dir=data_path, metric="seq_f1",label_list=ner_labels,delimiter=" "
)

# 3. Create a DataSilo that loads several datasets (train/dev/test), provides DataLoaders for them and calculates a few descriptive statistics of our datasets
data_silo = DataSilo(processor=processor, batch_size=batch_size)

# 4. Create an AdaptiveModel
# a) which consists of a pretrained language model as a basis
language_model = LanguageModel.load(lang_model)
# b) and a prediction head on top that is suited for our task => NER
prediction_head = TokenClassificationHead(task_name="ner",
                                          layer_dims=[768, len(processor.tasks["ner"]["label_list"])])

model = AdaptiveModel(
    language_model=language_model,
    prediction_heads=[prediction_head],
    embeds_dropout_prob=0.1,
    lm_output_types=["per_token"],
    device=device,
)

# 5. Create an optimizer
optimizer, warmup_linear = initialize_optimizer(
    model=model,
    learning_rate=2e-5,
    warmup_proportion=0.1,
    n_batches=len(data_silo.loaders["train"]),
    n_epochs=n_epochs,
)

# 6. Feed everything to the Trainer, which keeps care of growing our model into powerful plant and evaluates it from time to time
trainer = Trainer(
    optimizer=optimizer,
    data_silo=data_silo,
    epochs=n_epochs,
    n_gpu=n_gpu,
    warmup_linear=warmup_linear,
    evaluate_every=evaluate_every,
    device=device,
)

# 7. Let it grow
model = trainer.train(model)

# 8. Hooray! You have a model. Store it:
save_dir = "saved_models/bert-german-ner-tutorial"
model.save(save_dir)
processor.save(save_dir)


# 9. Load it & harvest your fruits (Inference)
basic_texts = [
    {"text": "Schartau sagte dem Tagesspiegel, dass Fischer ein Idiot sei"},
    {"text": "Martin Müller spielt Handball in Berlin"},
]
model = Inferencer.load(save_dir)
result = model.inference_from_dicts(dicts=basic_texts)
print(result)
