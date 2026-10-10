"""Pinned Qwen training path: retain context and skip ignored-label vocabulary logits."""
import torch
from transformers import Trainer, TrainingArguments
from datasets import Dataset


class SupervisedPositionTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        labels = inputs['labels']
        assert labels.shape[0] == 1, 'This verified loss path requires microbatch 1'
        assert self.label_smoother is None and self.compute_loss_func is None
        shift = torch.nn.functional.pad(labels, (0, 1), value=-100)[:, 1:]
        positions = torch.where(shift[0] != -100)[0]
        assert positions.numel() > 0, 'No supervised targets; do not invent a loss'
        augmented = dict(inputs, logits_to_keep=positions, shift_labels=shift[:, positions])
        return super().compute_loss(model, augmented, return_outputs, num_items_in_batch)


def training_components(tokenizer, output_dir):
    def collate(values):
        assert len(values) == 1, 'Only microbatch 1 is verified'
        return {k: torch.tensor([values[0][k]], dtype=torch.long)
                for k in ('input_ids', 'attention_mask', 'labels')}
    args = TrainingArguments(output_dir=str(output_dir), num_train_epochs=2,
        learning_rate=1e-4, per_device_train_batch_size=1, per_device_eval_batch_size=1,
        gradient_accumulation_steps=16, gradient_checkpointing=True,
        bf16=torch.cuda.is_bf16_supported(), fp16=not torch.cuda.is_bf16_supported(),
        optim='adamw_torch', lr_scheduler_type='linear', warmup_steps=.03,
        eval_strategy='epoch', save_strategy='epoch', logging_steps=5,
        report_to='none', seed=42, data_seed=42, load_best_model_at_end=False)
    return args, collate


def training_dataset(values):
    return Dataset.from_list([{k:v[k] for k in ('input_ids', 'attention_mask', 'labels')}
                              for v in values])
