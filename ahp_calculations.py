import numpy as np
import pandas as pd

def calculate_ahp(matrix):
    """Menghitung bobot AHP dari matriks perbandingan"""
    n = len(matrix)
    
    # Normalisasi matriks
    normalized = np.zeros((n, n))
    for j in range(n):
        col_sum = sum(matrix[:, j])
        for i in range(n):
            normalized[i, j] = matrix[i, j] / col_sum
    
    # Hitung bobot prioritas (eigen vector)
    weights = np.mean(normalized, axis=1)
    
    # Hitung lambda max
    lambda_max = np.sum(np.dot(matrix, weights) / weights) / n
    
    # Hitung Consistency Index (CI)
    ci = (lambda_max - n) / (n - 1)
    
    # Nilai Random Index (RI) berdasarkan ukuran matriks
    ri_dict = {1: 0, 2: 0, 3: 0.58, 4: 0.9, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
    ri = ri_dict.get(n, 1.49)
    
    # Hitung Consistency Ratio (CR)
    cr = ci / ri
    
    return weights, cr

def check_consistency(cr):
    """Memeriksa konsistensi matriks perbandingan"""
    return "Konsisten (CR < 0.1)" if cr < 0.1 else "Tidak Konsisten (CR ≥ 0.1). Silakan periksa kembali perbandingan."