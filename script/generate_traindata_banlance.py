import pandas as pd

# 读取数据
df = pd.read_csv('train_dataset.csv')

# 分离正负样本
df_pos = df[df['label'] == 1]
df_neg = df[df['label'] == 0]

# 决定保留多少负样本 (例如保留 3 倍的正样本数量)
neg_sample_count = int(len(df_pos) * 0) 

# 随机抽取负样本 (random_state 保证可复现)
df_neg_sampled = df_neg.sample(n=neg_sample_count, random_state=42)

# 合并并打乱顺序
df_balanced = pd.concat([df_pos, df_neg_sampled])
df_balanced = df_balanced.sample(frac=1, random_state=42).reset_index(drop=True)

# 保存新的训练集
df_balanced.to_csv('train_dataset_balanced.csv', index=False)

print(f"处理后正样本数: {len(df_pos)}")
print(f"处理后负样本数: {len(df_neg_sampled)}")
print(f"当前比例: 1 : {len(df_neg_sampled)/len(df_pos):.1f}")