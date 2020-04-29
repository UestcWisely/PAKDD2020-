import pandas as pd
import numpy as np
import lightgbm as lgb
import datetime
from tqdm import tqdm
import gc
from lightgbm.sklearn import LGBMClassifier
import pickle
import zipfile
import os
from scipy import interpolate

# 'smart_187raw'坏盘才有记录
# 'smart_5_normalized','smart_4_normalized', 'smart_12_normalized',
# 'smart_184_normalized',
# 'smart_188_normalized',
# 'smart_190raw',
# 'smart_192_normalized',
# 'smart_194_normalized',
# 'smart_197_normalized',
# 'smart_198_normalized'
## 处理data的记录时间戳，获得天，年，月，并将ts转换为时间格式
efficien_col = ['serial_number', 'manufacturer', 'model', 'smart_1_normalized',
                'smart_1raw', 'smart_3_normalized', 'smart_4raw', 'smart_5raw',
                'smart_7_normalized', 'smart_7raw', 'smart_9_normalized', 'smart_9raw',
                'smart_12raw', 'smart_184raw', 'smart_187_normalized',
                'smart_188raw', 'smart_189_normalized', 'smart_189raw',
                'smart_190_normalized', 'smart_191_normalized', 'smart_191raw',
                'smart_192raw', 'smart_193_normalized', 'smart_193raw', 'smart_194raw',
                'smart_195_normalized', 'smart_195raw', 'smart_197raw', 'smart_198raw',
                'smart_199raw', 'smart_240raw', 'smart_241raw', 'smart_242raw', 'dt', ]


# 'smart_187raw'坏盘才有记录
# 'smart_5_normalized','smart_4_normalized', 'smart_12_normalized',
# 'smart_184_normalized',
# 'smart_188_normalized',
# 'smart_190raw',
# 'smart_192_normalized',
# 'smart_194_normalized',
# 'smart_197_normalized',
# 'smart_198_normalized'
## 处理data的记录时间戳，获得天，年，月，并将ts转换为时间格式
def procese_dt(data):
    data = reduce_mem(data)
    data.dt = data.dt.apply(lambda x: datetime.datetime(x // 10000, (x // 100) % 100, x % 100).strftime('%Y-%m-%d'))
    data['dt'] = pd.to_datetime(data.dt)
    data = data.sort_values('dt').reset_index(drop=True)
    return data


### ------ 减少内存
def reduce_mem(df):
    start_mem = df.memory_usage().sum() / 1024 ** 2
    for col in df.columns:
        col_type = df[col].dtypes
        if (col_type != object) and (col_type != '<M8[ns]'):
            c_min = df[col].min()
            c_max = df[col].max()
            if str(col_type)[:3] == 'int':
                if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                    df[col] = df[col].astype(np.int8)
                elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                    df[col] = df[col].astype(np.int16)
                elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                    df[col] = df[col].astype(np.int32)
                elif c_min > np.iinfo(np.int64).min and c_max < np.iinfo(np.int64).max:
                    df[col] = df[col].astype(np.int64)
            else:
                if c_min > np.finfo(np.float16).min and c_max < np.finfo(np.float16).max:
                    df[col] = df[col].astype(np.float16)
                elif c_min > np.finfo(np.float32).min and c_max < np.finfo(np.float32).max:
                    df[col] = df[col].astype(np.float32)
                else:
                    df[col] = df[col].astype(np.float64)
    end_mem = df.memory_usage().sum() / 1024 ** 2
    print('{:.2f} Mb, {:.2f} Mb ({:.2f} %)'.format(start_mem, end_mem, 100 * (start_mem - end_mem) / start_mem))
    gc.collect()
    return df


def get_label(df, rate=3, mult=5, sample=False):
    # df.fault_time=df.fault_time.fillna('2019-01-01') # 给未坏的硬盘一个超前的日期
    #     df['fault_time'].fillna(value=datetime.datetime(2019,1,1),inplace=True)
    df['gap_bad_day'] = (df['fault_time'] - df['dt']).dt.days
    df['label'] = 0
    df.loc[df['gap_bad_day'] < 30, 'label'] = 10
    df.loc[df['gap_bad_day'] < 20, 'label'] = 20
    df.loc[df['gap_bad_day'] < 10, 'label'] = 30
    df.loc[df['gap_bad_day'] < 5, 'label'] = 40
    df.loc[df['gap_bad_day'] < 2, 'label'] = 100
    df.loc[df.label != 0, 'label'] = df.loc[df.label != 0, 'label'] + df.loc[df.label != 0, 'tag']
    #     df['label']=np.log1p(df['label'])

    #     df.loc[df['gap_bad_day']<30,'label']=10
    #     df.loc[df['gap_bad_day']<20,'label']=20
    #     df.loc[df['gap_bad_day']<10,'label']=30
    #     df.loc[df['gap_bad_day']<5,'label']=40
    #     df.loc[df['gap_bad_day']<2,'label']=100
    #  36.440
    # 这里看是设置gap少于多少天为正样本好
    #     del df['fault_time']
    return df


### 计算所有从差分特征，删除原始特征
def diff_test(df):
    # 根据特征重要性来
    # 输入的数据必须是已经按照时间排好序的 , smart_190_normalized，'smart_195_normalized','smart_192raw'
    # 位0 的diff  'smart_184raw' 'smart_193_normalized','smart_195raw'
    fts = ['smart_1_normalized',
           'smart_1raw', 'smart_5raw',
           'smart_7_normalized', 'smart_7raw',
           'smart_184raw', 'smart_187_normalized', 'smart_188raw',
           'smart_191_normalized', 'smart_191raw',
           'smart_193raw', 'smart_194raw',
           'smart_195_normalized', 'smart_195raw', 'smart_198raw',
           'smart_199raw']
    # 'smart_1raw','smart_1_normalized','smart_5raw','smart_187_normalized','smart_188raw','smart_195raw','smart_198raw', 'smart_199raw'

    tmp = df.loc[:, ['serial_number', 'model', 'dt'] + fts].groupby(['serial_number', 'model'])
    average = df.loc[:, ['serial_number', 'model']]

    for i in range(1, 8, 3):
        gap = (tmp['dt'].shift(0) - tmp['dt'].shift(i)).dt.days
        for col in fts:
            average['diff_{}_{}'.format(i, col)] = (tmp[col].shift(0) - tmp[col].shift(i)) / gap
    for col in fts:
        average['cumsum_diff_' + col] = average.groupby(['serial_number', 'model'])['diff_1_{}'.format(col)].cumsum()

    #     second_col=[k for k in average.columns if k not in ['serial_number','model']]
    #     for c in second_col:
    #         average['second_'+c]=tmp[c].shift(0)-tmp[c].shift(1)
    #         tmp2=sort_df.loc[:,['serial_number','model','dt']+diffs].drop_duplicates(['serial_number','model','dt']).reset_index(drop=True)
    #     df=df.merge(average, on=['serial_number','model','dt'], how='left')
    del tmp
    for k in fts:
        df['mean_diff_' + k] = average[['diff_{}_'.format(n) + k for n in range(1, 8, 3)]].mean(axis=1)
        df['cumsum_' + k] = average['cumsum_diff_' + k]
    #     average.drop(['serial_number','model'],axis=1,inplace=True)
    #     df=pd.concat([df,average],axis=1)
    del average
    return df


### 计算所有特征的初始差值：和serial配合使用
def init_test(df):
    df['server_time'] = (df['dt'] - df['init_dt']).dt.days
    diff_init = ['smart_1raw', 'smart_3_normalized', 'smart_5raw', 'smart_7_normalized', 'smart_7raw', 'smart_9raw',
                 'smart_12raw',
                 'smart_190_normalized', 'smart_191raw', 'smart_193raw', 'smart_194raw']
    #     #['smart_192raw','smart_193raw','smart_195_normalized','smart_241raw','smart_7raw']
    #  if c not in ['smart_184raw', 'smart_187_normalized','smart_188raw','smart_189raw',
    #        'smart_189_normalized','smart_240raw','smart_241raw','smart_242raw','smart_192raw','smart_1_normalized','smart_4raw']:
    ##'smart_193raw','smart_197raw','smart_198raw'
    for c in diff_init:
        df['init_diff_' + c] = df[c] - df['init_' + c]
        df.drop('init_' + c, axis=1, inplace=True)
    #         df.drop(c,axis=1,inplace=True)
    # #
    gc.collect()
    return df


## c窗函数
def window_feature(df, window=7):
    tmp = df.groupby(['serial_number', 'model']).rolling(window)

    col = ['smart_1_normalized', 'smart_7raw', 'smart_193raw', 'smart_195_normalized']
    # std
    tmp_var = tmp[col].std().reset_index(drop=True)
    tmp_var.columns = ['var_' + i for i in col]
    for c in col:
        df['var_diff_' + c] = df['mean_diff_' + c] * tmp_var['var_' + c]
    #     df=pd.concat([df,tmp_mean,tmp_max,tmp_std],axis=1)
    del tmp
    return df


## 计算损失率
def count_nan(df):
    tmp = df[['serial_number', 'model']]
    tmp['count'] = 1
    df['log_cusum'] = tmp.groupby(['serial_number', 'model'])['count'].transform(np.cumsum)
    df['miss_data_rate'] = 1 - df['log_cusum'] / ((df['dt'] - df['init_dt']).dt.days + 0.0001)
    del df['log_cusum']
    return df


## 预测为提交比赛的格式
# tag为标签文件，predict_df为提交文件,mon是评估的窗口月份
def outline_evalue(tag, predict_df, mon=6):
    tag['fault_time'] = pd.to_datetime(tag['fault_time'])
    # 只取最早的一天为准
    predict_df = predict_df.sort_values('dt')
    predict_df = predict_df.drop_duplicates(['serial_number', 'model'])
    #
    predict_df = predict_df.merge(tag, on=['serial_number', 'model'], how='left')
    predict_df['gap_day'] = (predict_df['fault_time'] - predict_df['dt']).dt.days
    ###npp:评估窗口内被预测出未来30天会坏的盘数
    npp = predict_df.shape[0]
    # ntpp:评估窗口内第一次预测故障的日期后30天内确实发生故障的盘数
    ntpp = predict_df.loc[predict_df['gap_day'] < 30].shape[0]
    # npr: 评估窗口内所有的盘故障数
    npr = sum(tag['fault_time'].dt.month == mon)
    # tpr: 评估窗口内故障盘被提前30天发现的数量
    tpr = predict_df.loc[(predict_df['fault_time'].dt.month == mon)].shape[0]
    ## ntpp/npp
    pricision = ntpp / npp
    # ntpr/npr
    recall = tpr / npr
    print('pricision:', pricision)
    print('recall:', recall)
    f1 = 2 * pricision * recall / (pricision + recall)
    print('f1*100 :', f1 * 100)
    return predict_df


### 填充nan
def cube_fill(df, model=1):
    '''
    model=1 插值raw
    model=0 插值 normal
    '''
    # if model :
    #     print('cubic to raw')
    #     col_feature=['smart_{}raw'.format(i) for i in [1,4,5,7,9,12,184,187,188,189,191,192,193,194,195,197,198,199]]
    # else:
    #     print('cubic to normalized')
    #     col_feature=['smart_{}_normalized'.format(i) for i in [1,3,7,9,187,189,190,191,193,195]]
    col_feature = [k for k in df.columns if k not in ['serial_number', 'manufacturer', 'model', 'dt']]
    for i in tqdm(col_feature):
        # print(i)
        tmp = df.groupby(['serial_number', 'model'])[i]
        df[i] = tmp.transform(chazhi)
    return df


def chazhi(x):
    org_y = np.array(x)
    new_x = np.array(range(len(x)))
    old_x = new_x[pd.notna(x)]
    old_y = org_y[pd.notna(x)]
    try:
        f = interpolate.interp1d(old_x, old_y, kind='cubic')
        return f(new_x)
    except:
        return x


def mark_score(df):
    score_col = ['smart_7raw', 'smart_9raw', 'smart_191raw', 'smart_193raw', 'smart_241raw', 'smart_242raw']
    tmp = df[['serial_number', 'model'] + score_col].groupby(['serial_number', 'model'])
    for i in score_col:
        df[i + '_quantile'] = tmp[i].expanding().quantile(0.75).reset_index(drop=True)
    for i in score_col:
        df[i + '_score'] = (df[i] - df['init_' + i]) / (df[i + '_quantile'] - df['init_' + i] + 1) * 100
        df.drop(i + '_quantile', axis=1, inplace=True)
    return df


def spare_feature(df):
    for i in ['smart_7raw_score', 'smart_9raw_score', 'smart_191raw_score',
              'smart_193raw_score', 'smart_241raw_score', 'smart_242raw_score']:
        tmp = pd.cut(df[i], bins=[-np.inf, -100, -60, -40, -20, 0, 20, 40, 60, 100, np.inf], labels=range(10))
        #     tmp=pd.qcut(df[i].values,q=10,labels=range(10),duplicates='drop')
        df[i + '_level'] = tmp.get_values()
    cross_cols = ['smart_7raw_score_level', 'smart_9raw_score_level', 'smart_191raw_score_level',
                  'smart_193raw_score_level', 'smart_241raw_score_level', 'smart_242raw_score_level']
    for i in range(len(cross_cols)):
        for j in range(i + 1, len(cross_cols)):
            df['cross_{}_{}'.format(cross_cols[i], cross_cols[j])] = np.int8(
                df[cross_cols[i]].values * 10 + df[cross_cols[j]].values)
    df.drop(cross_cols, axis=1, inplace=True)
    gc.collect()
    return df


def gather_erro(df):
    erro_cols = ['smart_187_normalized', 'smart_188raw', 'smart_184raw', 'smart_197raw', 'smart_198raw', 'smart_199raw',
                 'smart_241raw']  # 'smart_187_normalized',

    df['erro_mark'] = 0
    for m in erro_cols:
        df['erro_mark'] = df['erro_mark'] + df[m].values.astype('int32')
    return df


def gct_change(df):
    gct_col = ['smart_7raw', 'smart_3_normalized', 'smart_1raw', 'smart_5raw']  # smart_198raw
    tmp = df.groupby(['serial_number', 'model'])
    for col in gct_col:
        df['pct_' + col] = tmp[col].pct_change()
    return df


def get_mad(df):
    tmp = df.groupby(['serial_number', 'model'])
    mad_col = ['smart_1raw', 'smart_7raw', 'smart_3_normalized', 'smart_4raw', 'smart_9raw', 'smart_198raw']
    for col in mad_col:
        df['mad_' + col] = tmp[col].mad().reset_index(drop=True)
    return df


def ewm_calculate(df):
    ewm_col = ['smart_1raw', 'smart_1_normalized', 'smart_5raw', 'smart_187_normalized', 'smart_188raw', 'smart_195raw',
               'smart_198raw', 'smart_197raw', 'smart_199raw']
    tmp = df.groupby(['serial_number', 'model'])
    for col in tqdm(ewm_col):
        df['ewm_' + col + '_mean'] = tmp[col].transform(lambda x: pd.Series.ewm(x, span=7).mean())
        df['ewm_' + col + '_std'] = tmp[col].transform(lambda x: pd.Series.ewm(x, span=7).std())
    return df


def ewm_var_diff(df):
    for c in ['smart_1raw', 'smart_1_normalized', 'smart_5raw', 'smart_187_normalized', 'smart_188raw', 'smart_195raw',
              'smart_198raw', 'smart_199raw']:
        df['ewm_std_diff_' + c] = df['ewm_' + c + '_std'] * df['mean_diff_' + c]
    return df


def curr_rate(df):
    col = ['smart_4raw', 'smart_12raw', 'smart_192raw']
    df.dt = df['dt'].astype(str)
    tmp = df.groupby('dt')[col].quantile(0.99)
    tmp.reset_index(inplace=True)
    new_name = list(map(lambda x: 'curr_' + x, col))
    tmp.rename(columns=dict(zip(col, new_name)), inplace=True)
    df = df.merge(tmp[['dt'] + new_name], on='dt', how='left')
    del tmp
    for c in col:
        df['curr_rate_' + c] = df[c] / (df['curr_' + c] + 0.1)
        df.drop('curr_' + c, axis=1, inplace=True)
    df.dt = pd.to_datetime(df.dt)
    return df


def scale_smart(df):
    nums = [1, 7, 189, 191, 193, 195]
    for n in nums:
        df['scale_' + str(n)] = df['smart_{}raw'.format(n)] / (df['smart_{}_normalized'.format(n)] + 0.1)
    return df


# def data_smooth(x, alpha=20, beta=1):
#     tmp =x.shift(0)-( x.shift(1) * (alpha - beta) / alpha + x.shift(0) * beta / alpha)
#     return tmp

def data_smoother(df, features, alpha=20, beta=1):
    tmp = df.groupby(['serial_number', 'model'])
    for feature in features:
        df[feature + "_smooth"] = tmp[feature].shift(0) - (
                    tmp[feature].shift(1) * (alpha - beta) / alpha + tmp[feature].shift(0) * beta / alpha)
    return df

if __name__ == '__main__':
    ## 读取serial---------------
    serial = pd.read_csv('serial.csv')
    serial.init_dt = pd.to_datetime(serial.init_dt)
    gc.collect()
    paths=[]
    for i in range(51):
        paths.append('disk_sample_smart_log_{}_round2.csv'.format(
            (datetime.datetime(2018, 8, 11) + datetime.timedelta(days=i)).strftime('%Y%m%d')))
    data_9=pd.DataFrame()
    for p in paths:
        path='/tcdata/disk_sample_smart_log_round2/'+p
        data=pd.read_csv(path)
        data = data[efficien_col]
        data = procese_dt(data)
        data_9 = data_9.append(data).reset_index(drop=True)
    del data
    data_9.reset_index(drop=True,inplace=True)
    gc.collect()
    data_9=cube_fill(data_9)
    data_9.fillna(0, inplace=True)
    ## ---开始计算特征
    data_9['times'] = data_9['dt'].dt.month * 100 + data_9['dt'].dt.day
    print('curr rate ---')
    data_9 = curr_rate(data_9)
    tmp = data_9[['serial_number', 'times']]
    tmp['model_count'] = 1
    tmp = tmp.groupby(['serial_number', 'times'])['model_count'].sum().reset_index()
    data_9 = data_9.merge(tmp, on=['serial_number', 'times'], how='left')
    del tmp
    gc.collect()
    ## 计算 Init---
    print('calculate Init----')
    data_9 = data_9.merge(serial, how='left', on=['serial_number', 'model'])  #
    data_9 = init_test(data_9)
    # ## 计算 数据缺损率
    print('calculate nan rate ----')
    data_9 = count_nan(data_9)
    data_9 = gather_erro(data_9)
    print('calculate gct ----')
    data_9 = gct_change(data_9)
    # print('calculate window ----')
    # data_9=window_feature(data_9,window=7)
    # diff
    print('diff---')
    data_9 = diff_test(data_9)

    print('calculate ewm ----')
    data_9 = ewm_calculate(data_9)
    data_9 = ewm_var_diff(data_9)
    print('scale smart ----')
    data_9= scale_smart(data_9)
    features = ['smart_1_normalized', 'smart_5raw', 'smart_187_normalized', 'smart_188raw', 'smart_195raw',
                'smart_198raw', 'smart_197raw', 'smart_199raw']
    data_9 = data_smoother(data_9, features)
    data_9['serial_number'] = data_9['serial_number'].apply(lambda x: int(x.split('_')[1]))  # 处理serial

    # data_9['times'] = data_9['dt'].dt.month * 100 + data_9['dt'].dt.day
    # for col in ['smart_7raw', 'smart_9raw', 'smart_241raw', 'smart_242raw', 'smart_191raw', 'smart_193raw']:
    #     data_9[col] = data_9[col] / data_9['times']
    # del data_9['times']
    # data_9=data_9.loc[data_9['dt'].dt.month==9]
    smartcol = sorted([col for col in data_9.columns if col not in ['dt', 'fault_time',
                                                                        'tag', 'label', 'gap_bad_day', 'manufacturer',
                                                                        'init_dt', 'init_smart_192raw', 'smart_4raw',
                                                                        'smart_195raw'
        , 'smart_12raw', 'smart_1_normalized', 'smart_190_normalized', 'times', 'serial_number', 'model']])

#     smartcol = [col for col in data_9.columns if col not in ['dt','fault_time',
#     'tag','label','gap_bad_day','manufacturer','init_dt','serial_number','init_smart_192raw','smart_4raw','smart_195raw','smart_12raw','smart_194raw'
# 'smart_1raw','smart_1_normalized','smart_190_normalized','model']]

    # 'mean_diff_smart_1_normalized' ,,'mean_diff_smart_1raw',
    # 'init_diff_smart_192raw' 有毒？
    #  'init_diff_smart_193raw'   |


    print('测试集Log总数',data_9.shape[0])
    with open('tag_model.pkl', 'rb') as fr:
        tag_model = pickle.load(fr)
    tag_pred=np.argmax(tag_model.predict_proba(data_9[smartcol]),axis=1)
    data_9['tag_predict']=tag_pred
    smartcol+=['tag_predict']
    print('training feature:', smartcol)
    print(len(smartcol))
    #------------- ensemble
    # weight_iteration=[0.77777778, 0.77394636]
    best_iter=[58,59]
    pred=0
    for index,b_t in enumerate(best_iter,1):
        with open('ensenble_lgb{}_{}.pkl'.format(index,b_t), 'rb') as fr:
            clf = pickle.load(fr)
        pred+=clf.predict(data_9[smartcol])/2
    # tmp=np.nan_to_num(data_9[smartcol].values).astype('float32')
    # data_9['predict']=clf.predict_proba(tmp)[:,1]
    data_9['predict'] = pred
    #-------------------------
    # sub=data_9[['serial_number','model','dt','predict']]
    # t0=0.2
    # v = 0.02
    # best_t = t0
    # for step in range(1000):
    #     curr_t = t0 + step * v
    #     sub['label'] = [1 if x >= curr_t else 0 for x in sub['predict']]
    #     curr_len=len(sub.loc[sub.label==1].drop_duplicates(['serial_number','model']))
    #     print('step: {} threshold: {} number:{}'.format(step, curr_t,curr_len))
    #     if curr_len <=200:
    #         best_t = curr_t
    #         print('step: {}   best threshold: {}'.format(step, best_t))
    #         break
    #
    # data_9['label'] = [1 if x >= best_t else 0 for x in data_9['predict']]

    # data_9=data_9.loc[data_9['label']==1]
    # print('predict number:',data_9.shape[0])
    # data_9.serial_number = data_9.serial_number.apply(lambda x: 'disk_' + str(x))
    # data_9.loc[:,['manufacturer', 'model', 'serial_number','dt']].to_csv('result.csv',index=False,header=False)
    # os.system('zip result.zip result.csv')
    #-------------------------------------------------------
    ###新策略评估阈值：
    #
    # sub = data_9[['manufacturer','model', 'serial_number', 'dt', 'predict']]
    # sub['id'] = sub['serial_number'] * 10 + sub['model']
    # # dayss = sorted(sub['dt'].dt.day.unique())
    # final_result = pd.DataFrame()
    # select_data = {}
    # last_curr = pd.DataFrame()
    # throsed = 999
    # # 一天天的数据预测
    # for i in range(37):
    #     count_n=0
    #     date_dt=datetime.datetime(2018,8,25)+datetime.timedelta(days=i)
    #     curr_data = sub.loc[sub['dt']== date_dt]
    #     curr_data['rank'] = curr_data['predict'].rank(ascending=False)
    #     new_curr = curr_data.loc[curr_data['rank'] < 20]
    #     new_id = new_curr['id'].values
    #     for s in new_id:
    #         select_data[s] = select_data.setdefault(s, 0) + 1
    #         tmp = new_curr.loc[new_curr['id'] == s]
    #         if select_data[s] >= 2 or tmp['predict'].values[0] >= throsed:
    #             final_result = final_result.append(tmp)
    #             count_n+=1
    #     # 跟新阈值
    #     if final_result.shape[0] > 0:
    #         #         print(throsed)
    #         throsed = final_result['predict'].min()
    #     # 回溯前一天中未被召回的样本
    #     if last_curr.shape[0] > 0:
    #         final_result = final_result.append(last_curr.loc[last_curr['predict'] >= throsed])
    #     last_curr = curr_data
    #     print('当天投置数 time {}：{}'.format(date_dt,count_n))
  ##### 最新策略评估-----------------

    sub = data_9[['manufacturer','model', 'serial_number', 'dt', 'predict']]
    sub['id'] = sub['serial_number'] * 10 + sub['model']
    # dayss = sorted(sub['dt'].dt.day.unique())
    final_result = pd.DataFrame()
    select_data = {}
    last_curr = pd.DataFrame()
    # 一天天的数据预测
    throsed1 = 999
    throsed2 = 999
    last_curr1=pd.DataFrame()
    last_curr2 = pd.DataFrame()
    model1_nn = sub.loc[sub.model == 1].shape[0]
    model2_nn = sub.loc[sub.model == 2].shape[0]
    print('all model1:{}  model2:{}'.format(model1_nn,model2_nn))
    for i in range(34):
        date_dt = datetime.datetime(2018, 8, 28) + datetime.timedelta(days=i)
        curr_data = sub.loc[sub['dt']== date_dt]
        # curr_data = sub.loc[sub['dt'].dt.day == d]
        model1_disk = curr_data.loc[curr_data.model == 1]
        model2_disk = curr_data.loc[curr_data.model == 2]
        model1_disk['rank'] = model1_disk['predict'].rank(ascending=False)
        model2_disk['rank'] = model2_disk['predict'].rank(ascending=False)

        new_curr = pd.DataFrame()
        nn1 = np.round(model1_disk.shape[0]/model1_nn*680)
        nn2 = np.round(model2_disk.shape[0] /model2_nn*680)
        print('{} day log number:{} model1:{} model2:{}'.format(date_dt,curr_data.shape[0],
                                        model1_disk.shape[0],model2_disk.shape[0]))
        print('nn1:{:.4f} nn2:{:.4f}'.format(nn1, nn2))
        new_curr = new_curr.append(model1_disk.loc[model1_disk['rank'] < nn1])
        new_curr = new_curr.append(model2_disk.loc[model2_disk['rank'] < nn2])
        new_id = new_curr['id'].values
        count=0
        for s in new_id:
            select_data[s] = select_data.setdefault(s, 0) + 1
            tmp = new_curr.loc[new_curr['id'] == s]
            if select_data[s] >= 2:
                final_result = final_result.append(tmp)
                count+=1
            elif ((tmp['model'].values[0] == 1) and (tmp['predict'].values[0] >= throsed1)) or ((tmp['model'
                     ].values[0] == 2) and (tmp['predict'].values[0] >= throsed2)):
                final_result = final_result.append(tmp)
                count+=1
        print('投票:',count)
        # 跟新阈值
        if final_result.shape[0] > 0:
            #         print(throsed)
            throsed1 = final_result.loc[final_result.model == 1]['predict'].min()
            throsed2 = final_result.loc[final_result.model == 2]['predict'].min()
        # 回溯前一天中未被召回的样本
        if last_curr1.shape[0]  or last_curr2.shape[0]> 0:
            final_result = final_result.append(last_curr.loc[last_curr1['predict'] >= throsed1])
            final_result = final_result.append(last_curr.loc[last_curr2['predict'] >= throsed2])
        last_curr1 = model1_disk
        last_curr2 = model2_disk

    # data_9 = data_9.loc[data_9['dt'].dt.month == 9]
    # sub = data_9[['manufacturer','model', 'serial_number', 'dt', 'predict']]
    # sub['id'] = sub['serial_number'] * 10 + sub['model']
    # dayss = sorted(sub['dt'].dt.day.unique())
    # final_result = pd.DataFrame()
    # select_data = {}
    # last_curr = pd.DataFrame()
    # throsed = 999
    # # 一天天的数据预测
    # # data6_model1_scale=np.round(np.array(data8_model1)/sum(data8_model1)*70)
    # # data6_model2_scale=np.round(np.array(data8_model2)/sum(data8_model2)*70)
    # model1_nn = sub.loc[sub.model == 1].shape[0]
    # model2_nn = sub.loc[sub.model == 2].shape[0]
    # for d in dayss:
    #     curr_data = sub.loc[sub['dt'].dt.day == d]
    #     model1_disk = curr_data.loc[curr_data.model == 1]
    #     model2_disk = curr_data.loc[curr_data.model == 2]
    #     model1_disk['rank'] = model1_disk['predict'].rank(ascending=False)
    #     model2_disk['rank'] = model2_disk['predict'].rank(ascending=False)
    #     nn1 = np.round((75 * model1_disk.shape[0] / model1_nn))
    #     nn2 = np.round((75 * model2_disk.shape[0] / model2_nn))
    #     print('nn1:{} nn2:{}'.format(nn1, nn2))
    #     tmp = pd.concat([model1_disk.loc[model1_disk['rank'] <= nn1], model2_disk.loc[model2_disk['rank'] <= nn2]],
    #                     axis=0)
    #     final_result = final_result.append(tmp)
    #     sub = sub.loc[~sub.id.isin(tmp.id)]

    # 去除重复取的记录
    final_result.drop_duplicates(['serial_number', 'model', 'dt'], inplace=True)
    final_result.serial_number = final_result.serial_number.apply(lambda x: 'disk_' + str(x))
    final_result=final_result.loc[final_result['dt'].dt.month==9]
    ##评估保存
    disk_len = len(final_result.drop_duplicates(['serial_number', 'model']))# 提交文件不去重

    print('disk number:', disk_len)
    print('data len :', final_result.shape[0])
    final_result.loc[:, ['manufacturer','model','serial_number','dt']].to_csv('result.csv', index=False, header=False)
    os.system('zip result.zip result.csv')
    #---------------------------------------

