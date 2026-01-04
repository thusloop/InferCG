"""
尚未未测试
"""

import os
import torch
import pandas as pd
import numpy as np
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification, AdamW, get_linear_schedule_with_warmup
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from tqdm import tqdm

# =================配置参数=================
class Config:
    # 模型名称，可随意更换为其他 HuggingFace 模型
    # CodeBERT: "microsoft/codebert-base"
    # GraphCodeBERT: "microsoft/graphcodebert-base"
    # RoBERTa: "roberta-base"
    # 注意：CodeT5是生成式模型(Seq2Seq)，直接用SequenceClassification头可能不兼容，
    # 若要用CodeT5做分类，通常只取其Encoder部分或使用T5EncoderModel，这里默认支持BERT类架构。
    MODEL_NAME = "microsoft/codebert-base"
    
    # 文件路径
    TRAIN_FILE = "train_dataset_balanced.csv"
    TEST_FILE = "test_dataset.csv"
    OUTPUT_DIR = "./saved_model"
    PREDICT_FILE = "test_dataset_predict.csv"
    
    # 训练超参数
    MAX_LEN = 512       # CodeBERT 最大支持 512
    BATCH_SIZE = 32      # 根据显存大小调整，显存小改小，显存大改大
    EPOCHS = 5          # 训练轮数
    LEARNING_RATE = 2e-5
    SEED = 42
    VALID_SIZE = 0.1    # 训练集中划分出验证集的比例

    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# =================数据处理类=================
class CallGraphDataset(Dataset):
    def __init__(self, df, tokenizer, max_len):
        self.df = df
        self.tokenizer = tokenizer
        self.max_len = max_len
        
        # 提取各个列，并处理可能的空值
        self.callers = df['caller'].fillna("").astype(str).tolist()
        self.callees = df['callee'].fillna("").astype(str).tolist()
        self.caller_codes = df['caller_code'].fillna("").astype(str).tolist()
        self.callee_codes = df['callee_code'].fillna("").astype(str).tolist()
        self.caller_paths = df['caller_path'].fillna("").astype(str).tolist()
        self.callee_paths = df['callee_path'].fillna("").astype(str).tolist()
        
        # 如果是测试集预测阶段，可能没有 label 列（虽然你的测试集有）
        if 'label' in df.columns:
            self.labels = df['label'].tolist()
        else:
            self.labels = [0] * len(df) # 占位

    def __len__(self):
        return len(self.df)

    def __getitem__(self, item):
        # 构造输入格式
        # 策略：将 Caller 信息和 Callee 信息拼接
        # Input A: Caller Name + Path + Code
        # Input B: Callee Name + Path + Code
        # Tokenizer 会自动处理为 [CLS] Input A [SEP] Input B [SEP]
        
        input_text_a = f"Caller: {self.callers[item]} Path: {self.caller_paths[item]} Code: {self.caller_codes[item]}"
        input_text_b = f"Callee: {self.callees[item]} Path: {self.callee_paths[item]} Code: {self.callee_codes[item]}"

        encoding = self.tokenizer.encode_plus(
            input_text_a,
            input_text_b,
            add_special_tokens=True,
            max_length=self.max_len,
            return_token_type_ids=True,
            padding='max_length',
            truncation=True, # 超出 512 的部分会被截断
            return_attention_mask=True,
            return_tensors='pt',
        )

        return {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'token_type_ids': encoding['token_type_ids'].flatten(),
            'labels': torch.tensor(self.labels[item], dtype=torch.long)
        }

# =================辅助函数=================
def set_seed(seed):
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    torch.backends.cudnn.deterministic = True

def compute_metrics(preds, labels):
    # preds: model outputs (logits)
    # labels: true labels
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
    
    # 1. 加载 Tokenizer 和 模型
    # AutoModelForSequenceClassification 会自动加载预训练权重并在顶部添加一个二分类层
    print(f"Loading model: {Config.MODEL_NAME}...")
    tokenizer = AutoTokenizer.from_pretrained(Config.MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(Config.MODEL_NAME, num_labels=2)
    model.to(Config.DEVICE)
    
    # 2. 读取数据
    print("Reading CSV files...")
    df_train_full = pd.read_csv(Config.TRAIN_FILE)
    df_test = pd.read_csv(Config.TEST_FILE)
    
    # 划分训练集和验证集 (从 train_dataset_balanced.csv 中切分)
    df_train, df_val = train_test_split(df_train_full, test_size=Config.VALID_SIZE, random_state=Config.SEED, stratify=df_train_full['label'])
    
    print(f"Train size: {len(df_train)}, Val size: {len(df_val)}, Test size: {len(df_test)}")
    
    # 3. 创建 DataLoader
    train_dataset = CallGraphDataset(df_train, tokenizer, Config.MAX_LEN)
    val_dataset = CallGraphDataset(df_val, tokenizer, Config.MAX_LEN)
    test_dataset = CallGraphDataset(df_test, tokenizer, Config.MAX_LEN)
    
    train_loader = DataLoader(train_dataset, batch_size=Config.BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=Config.BATCH_SIZE)
    test_loader = DataLoader(test_dataset, batch_size=Config.BATCH_SIZE)
    
    # 4. 优化器和调度器
    optimizer = AdamW(model.parameters(), lr=Config.LEARNING_RATE, correct_bias=False)
    total_steps = len(train_loader) * Config.EPOCHS
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=0,
        num_training_steps=total_steps
    )
    
    # 5. 训练循环
    best_accuracy = 0.0
    
    for epoch in range(Config.EPOCHS):
        print(f"\n======== Epoch {epoch + 1}/{Config.EPOCHS} ========")
        
        # --- Training ---
        model.train()
        total_train_loss = 0
        
        progress_bar = tqdm(train_loader, desc="Training")
        for batch in progress_bar:
            input_ids = batch['input_ids'].to(Config.DEVICE)
            attention_mask = batch['attention_mask'].to(Config.DEVICE)
            token_type_ids = batch['token_type_ids'].to(Config.DEVICE)
            labels = batch['labels'].to(Config.DEVICE)
            
            model.zero_grad()
            
            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                token_type_ids=token_type_ids,
                labels=labels
            )
            
            loss = outputs.loss
            total_train_loss += loss.item()
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0) # 梯度裁剪防止爆炸
            optimizer.step()
            scheduler.step()
            
            progress_bar.set_postfix({'loss': loss.item()})
            
        avg_train_loss = total_train_loss / len(train_loader)
        print(f"Average Train Loss: {avg_train_loss:.4f}")
        
        # --- Evaluation on Test Set (按要求每个epoch都在测试集测试) ---
        print("Running Evaluation on Test Set...")
        model.eval()
        
        all_preds = []
        all_labels = []
        
        with torch.no_grad():
            for batch in tqdm(test_loader, desc="Evaluating"):
                input_ids = batch['input_ids'].to(Config.DEVICE)
                attention_mask = batch['attention_mask'].to(Config.DEVICE)
                token_type_ids = batch['token_type_ids'].to(Config.DEVICE)
                labels = batch['labels'].to(Config.DEVICE)
                
                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    token_type_ids=token_type_ids
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
        
        # --- 保存准确率最高的模型 ---
        # 按照要求，基于测试集的 Accuracy 保存
        if metrics['accuracy'] > best_accuracy:
            best_accuracy = metrics['accuracy']
            print(f"New Best Model! Saving to {Config.OUTPUT_DIR}...")
            
            if not os.path.exists(Config.OUTPUT_DIR):
                os.makedirs(Config.OUTPUT_DIR)
            
            # 保存模型和tokenizer
            model.save_pretrained(Config.OUTPUT_DIR)
            tokenizer.save_pretrained(Config.OUTPUT_DIR)
            
            # --- 保存该最佳 Epoch 的预测结果到 CSV ---
            print(f"Saving predictions to {Config.PREDICT_FILE}...")
            df_test_copy = df_test.copy()
            df_test_copy['prediction'] = pred_classes
            # quoting=1 (QUOTE_ALL) 保证格式安全
            df_test_copy.to_csv(Config.PREDICT_FILE, index=False, quoting=1, encoding='utf-8-sig')

    print("\nTraining complete.")
    print(f"Best Test Accuracy: {best_accuracy:.4f}")

if __name__ == "__main__":
    main()