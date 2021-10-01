
# Limit numpy's number of threads
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"

# Base imports
import itertools
import json
import math
from multiprocessing import Pool
import numpy as np
import pandas as pd
import scipy
from scipy import stats
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPRegressor
from sklearn.svm import SVR

# Code imports
import sys
sys.path.insert(0, "/home/gregory/Desktop/MAPLE/Code/")

from maple.MAPLE import MAPLE
from maple.Misc import load_normalize_data, unpack_coefs

from lime import lime_tabular

###
# Run Experiments
###

def fit_rf(X_train, y_train, X_test, y_test, n_estimators = 100, max_features = 0.5, min_samples_leaf = 5):
    rf = RandomForestRegressor(n_estimators = n_estimators, min_samples_leaf = min_samples_leaf, max_features = max_features)
    rf.fit(X_train, y_train)
    return rf

def fit_nn(X_train, y_train, X_test, y_test):
    nn = MLPRegressor(max_iter = 500)
    nn.fit(X_train, y_train)
    return nn

def fit_svr(X_train, y_train, X_test, y_test):
    nn = SVR()
    nn.fit(X_train, y_train)
    return nn

datasets = ["autompgs", "happiness", "winequality-red", "housing", "day", "crimes", "music", "communities"]
trials = []
for i in range(25):
    trials.append(i + 1)
args = itertools.product(trials, datasets)

def run(args):
    # Hyperparamaters
    num_perturbations = 5
    
    # Fixes an issue where threads of inherit the same rng state
    scipy.random.seed()
    
    # Arguments
    dataset = args[1]
    trial = args[0]
    
    # Outpt
    out = {}
    file = open("Trials/" + dataset + "_" + str(trial) + ".json", "w")

    # Load data
    X_train, y_train, X_valid, y_valid, X_test, y_test, train_mean, train_stddev = load_normalize_data("../Datasets/" + dataset + ".csv")
    n = X_test.shape[0]
    d = X_test.shape[1]
    
    scales = [0.1, 0.25]
    scales_len = len(scales)
        
    # Fit model
    model = fit_svr(X_train, y_train, X_test, y_test)
    out["model_rmse"] = np.sqrt(np.mean((y_test - model.predict(X_test))**2))
        
    # Fit LIME and MAPLE explainers to the model
    exp_lime = lime_tabular.LimeTabularExplainer(X_train, discretize_continuous=False, mode="regression")
    exp_maple = MAPLE(X_train, model.predict(X_train), X_valid, model.predict(X_valid))
        
    # Evaluate model faithfullness on the test set
    lime_rmse = np.zeros((scales_len))
    maple_rmse = np.zeros((scales_len))
    
    for i in range(n):
        x = X_test[i, :]
        
        coefs_lime = unpack_coefs(exp_lime, x, model.predict, d, X_train) #Allow full number of features
    
        e_maple = exp_maple.explain(x)
        coefs_maple = e_maple["coefs"]
        
        for j in range(num_perturbations):
            
            noise = np.random.normal(loc = 0.0, scale = 1.0, size = d)
            
            for k in range(scales_len):
                scale = scales[k]
            
                x_pert = x + scale * noise
            
                model_pred = model.predict(x_pert.reshape(1,-1))
                lime_pred = np.dot(np.insert(x_pert, 0, 1), coefs_lime)
                maple_pred = np.dot(np.insert(x_pert, 0, 1), coefs_maple)
            
                lime_rmse[k] += (lime_pred - model_pred)**2
                maple_rmse[k] += (maple_pred - model_pred)**2

    lime_rmse /= n * num_perturbations
    maple_rmse /= n * num_perturbations

    lime_rmse = np.sqrt(lime_rmse)
    maple_rmse = np.sqrt(maple_rmse)

    out["lime_rmse_0.1"] = lime_rmse[0]
    out["maple_rmse_0.1"] = maple_rmse[0]
    out["lime_rmse_0.25"] = lime_rmse[1]
    out["maple_rmse_0.25"] = maple_rmse[1]

    json.dump(out, file)
    file.close()

pool = Pool(12)
pool.map(run, args)

#for i in args:
#    run(i)

###
# Merge Results
###

with open("Trials/" + datasets[0] + "_" + str(trials[0]) + ".json") as f:
    data = json.load(f)

columns = list(data.keys())
df = pd.DataFrame(0, index = datasets, columns = columns)

for dataset in datasets:
    for trial in trials:
        with open("Trials/" + dataset + "_" + str(trial) + ".json") as f:
            data = json.load(f)
        for name in columns:
            df.ix[dataset, name] += data[name] / len(trials)

df.to_csv("results.csv")

###
# Stat Testing
###

file = open("stats.txt", "w")

with open("Trials/" + datasets[0] + "_" + str(trials[0]) + ".json") as f:
    data = json.load(f)

columns = list(data.keys())
df = pd.DataFrame(index = datasets, columns = columns)
df = df.apply(lambda x:x.apply(lambda x:[] if math.isnan(x) else x))

for dataset in datasets:
    for trial in trials:
        with open("Trials/" + dataset + "_" + str(trial) + ".json") as f:
            data = json.load(f)
        for name in columns:
            df.ix[dataset, name].append(data[name])

    file.write(dataset + "\n")
    file.write("Sigma = 0.1: " + str(stats.ttest_ind(df.ix[dataset, "lime_rmse_0.1"],df.ix[dataset, "maple_rmse_0.1"], equal_var = False).pvalue) + "\n")
    file.write("Sigma = 0.25: " + str(stats.ttest_ind(df.ix[dataset, "lime_rmse_0.25"],df.ix[dataset, "maple_rmse_0.25"], equal_var = False).pvalue) + "\n")

file.close()
