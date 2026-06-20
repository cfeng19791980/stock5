with open(r'E:\stock5\backtest_full_pipeline.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '总准确率' in line and 'tech_score' in line:
        print(f'Found at line {i+1}: {repr(line)}')
        lines[i] = 'print(f"{0:<22} {1:>11.1f}% {2:>11.1f}%".format("总准确率", ((df_r["tech_score"]>=60)==df_r["actual_up"]).mean()*100, ((df_r["risk_adjusted"]>=60)==df_r["actual_up"]).mean()*100))\n'
        print(f'Replaced with: {repr(lines[i])}')
        break

with open(r'E:\stock5\backtest_full_pipeline.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Done')
