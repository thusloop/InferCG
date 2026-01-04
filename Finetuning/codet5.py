import os
import torch
import pandas as pd
import numpy as np
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from tqdm import tqdm

# =================配置参数=================
class Config:
    # 修改模型名称为 CodeT5
    MODEL_NAME = "Salesforce/codet5-base"
    
    # 文件路径 (保持你的路径)
    TRAIN_FILE = "../train_dataset_balanced.csv"
    TEST_FILE = "../test_dataset.csv"
    OUTPUT_DIR = "./saved_model"
    PREDICT_FILE = "test_dataset_predict.csv"
    
    # 训练超参数
    MAX_LEN = 512       
    BATCH_SIZE = 16      # CodeT5 比 CodeBERT 稍微耗显存一些，如果OOM(显存不足)请调小，如 8 或 4
    EPOCHS = 15          
    LEARNING_RATE = 2e-5
    SEED = 42
    VALID_SIZE = 0.001   

    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# =================数据处理类=================
class CallGraphDataset(Dataset):
    def __init__(self, df, tokenizer, max_len):
        self.df = df
        self.tokenizer = tokenizer
        self.max_len = max_len
        
        self.callers = df['caller'].fillna("").astype(str).tolist()
        self.callees = df['callee'].fillna("").astype(str).tolist()
        self.caller_codes = df['caller_code'].fillna("").astype(str).tolist()
        self.callee_codes = df['callee_code'].fillna("").astype(str).tolist()
        self.caller_paths = df['caller_path'].fillna("").astype(str).tolist()
        self.callee_paths = df['callee_path'].fillna("").astype(str).tolist()
        
        if 'label' in df.columns:
            self.labels = df['label'].tolist()
        else:
            self.labels = [0] * len(df)

    def __len__(self):
        return len(self.df)

    def __getitem__(self, item):
        # 构造输入格式
        # T5 不需要 token_type_ids，直接拼接即可
        input_text_a = f"Caller: {self.callers[item]} Path: {self.caller_paths[item]} Code: {self.caller_codes[item]}"
        input_text_b = f"Callee: {self.callees[item]} Path: {self.callee_paths[item]} Code: {self.callee_codes[item]}"

        encoding = self.tokenizer.encode_plus(
            input_text_a,
            input_text_b,
            add_special_tokens=True,
            max_length=self.max_len,
            return_token_type_ids=False, # CodeT5 (T5) 不需要这个
            padding='max_length',
            truncation=True,
            return_attention_mask=True,
            return_tensors='pt',
        )

        # 移除 token_type_ids 的返回
        return {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'labels': torch.tensor(self.labels[item], dtype=torch.long)
        }

# =================辅助函数=================
def set_seed(seed):
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    torch.backends.cudnn.deterministic = True

def compute_metrics(preds, labels):
    preds_flat = np.argmax(preds, axis=1).flatten()
    labels_flat = labels.flatten()
    
    precision, recall, f1, _ = precision_recall_fscore_support(labels_flat, preds_flat, average='binary')
    acc = accuracy_score(labels_flat, preds_flat)
    
    return {
        'accuracy': acc,
        'precision': precision,
        'recall': recall,
        'f1': f1
    }, preds_flat

# =================主流程=================
def main():
    set_seed(Config.SEED)
    print(f"Using device: {Config.DEVICE}")
    
    print(f"Loading model: {Config.MODEL_NAME}...")
    tokenizer = AutoTokenizer.from_pretrained(Config.MODEL_NAME)
    
    # AutoModelForSequenceClassification 支持 CodeT5，会自动加载 T5ForSequenceClassification
    model = AutoModelForSequenceClassification.from_pretrained(Config.MODEL_NAME, num_labels=2)
    model.to(Config.DEVICE)
    
    print("Reading CSV files...")
    df_train_full = pd.read_csv(Config.TRAIN_FILE)
    df_test = pd.read_csv(Config.TEST_FILE)
    
    # 保持你原有的数据划分逻辑
    df_train, df_val = train_test_split(df_train_full, test_size=Config.VALID_SIZE, random_state=Config.SEED, stratify=df_train_full['label'])
    
    # 你的自定义数据混合逻辑
    df_train = pd.concat([df_train, df_val, df_test[1191:5597]], ignore_index=True)
    df_test = pd.concat([df_test[:1191], df_test[5597:]], ignore_index=True)
    
    print(f"Train size: {len(df_train)}, Val size: {len(df_val)} (Ignored in logic), Test size: {len(df_test)}")
    
    train_dataset = CallGraphDataset(df_train, tokenizer, Config.MAX_LEN)
    # 注意：这里的 val_dataset 实际上在你上面的逻辑里被合并进 train 了，或者没有被使用
    # 为了代码完整性保留，但实际 loop 中只用了 train_loader 和 test_loader
    val_dataset = CallGraphDataset(df_val, tokenizer, Config.MAX_LEN) 
    test_dataset = CallGraphDataset(df_test, tokenizer, Config.MAX_LEN)
    
    train_loader = DataLoader(train_dataset, batch_size=Config.BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=Config.BATCH_SIZE)
    test_loader = DataLoader(test_dataset, batch_size=Config.BATCH_SIZE)
    
    optimizer = torch.optim.AdamW(model.parameters(), lr=Config.LEARNING_RATE)
    total_steps = len(train_loader) * Config.EPOCHS
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=0,
        num_training_steps=total_steps
    )
    
    best_f1 = 0.0
    
    for epoch in range(Config.EPOCHS):
        print(f"\n======== Epoch {epoch + 1}/{Config.EPOCHS} ========")
        
        # --- Training ---
        model.train()
        total_train_loss = 0
        
        progress_bar = tqdm(train_loader, desc="Training")
        for batch in progress_bar:
            input_ids = batch['input_ids'].to(Config.DEVICE)
            attention_mask = batch['attention_mask'].to(Config.DEVICE)
            # 移除了 token_type_ids
            labels = batch['labels'].to(Config.DEVICE)
            
            model.zero_grad()
            
            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels
            )
            
            loss = outputs.loss
            total_train_loss += loss.item()
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            
            progress_bar.set_postfix({'loss': loss.item()})
            
        avg_train_loss = total_train_loss / len(train_loader)
        print(f"Average Train Loss: {avg_train_loss:.4f}")
        
        # --- Evaluation on Test Set ---
        print("Running Evaluation on Test Set...")
        model.eval()
        
        all_preds = []
        all_labels = []
        
        with torch.no_grad():
            for batch in tqdm(test_loader, desc="Evaluating"):
                input_ids = batch['input_ids'].to(Config.DEVICE)
                attention_mask = batch['attention_mask'].to(Config.DEVICE)
                # 移除了 token_type_ids
                labels = batch['labels'].to(Config.DEVICE)
                
                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask
                )
                
                logits = outputs.logits
                all_preds.append(logits.cpu().numpy())
                all_labels.append(labels.cpu().numpy())
        
        all_preds = np.concatenate(all_preds, axis=0)
        all_labels = np.concatenate(all_labels, axis=0)
        
        metrics, pred_classes = compute_metrics(all_preds, all_labels)
        
        print(f"Test Accuracy:  {metrics['accuracy']:.4f}")
        print(f"Test Precision: {metrics['precision']:.4f}")
        print(f"Test Recall:    {metrics['recall']:.4f}")
        print(f"Test F1 Score:  {metrics['f1']:.4f}")
        
        # --- Save Best Model ---
        if metrics['f1'] > best_f1:
            best_f1 = metrics['f1']
            print(f"New Best Model (F1: {best_f1:.4f})! Saving to {Config.OUTPUT_DIR}...")
            
            if not os.path.exists(Config.OUTPUT_DIR):
                os.makedirs(Config.OUTPUT_DIR)
            
            model_path = os.path.join(Config.OUTPUT_DIR, "best_model_t5.pth")
            torch.save(model, model_path)
            
            # 保存预测结果
            print(f"Saving predictions to {Config.PREDICT_FILE}...")
            df_test_copy = df_test.copy()
            df_test_copy['prediction'] = pred_classes
            df_test_copy.to_csv(Config.PREDICT_FILE, index=False, quoting=1, encoding='utf-8-sig')

    print("\nTraining complete.")
    print(f"Best Test f1: {best_f1:.4f}")

if __name__ == "__main__":
    main()