import numpy as np
import pandas as pd
from utils.db_functions import *

def calculate_ahp(matrix):
    """Menghitung seluruh komponen AHP"""
    n = matrix.shape[0]
    
    # Hitung nilai eigen
    eigenvalues, eigenvectors = np.linalg.eig(matrix)
    max_eigenvalue = np.max(eigenvalues.real)
    max_eigenvector = eigenvectors[:, np.argmax(eigenvalues.real)].real
    
    # Normalisasi vektor eigen
    weights = max_eigenvector / np.sum(max_eigenvector)
    
    # Hitung indeks konsistensi
    ci = (max_eigenvalue - n) / (n - 1)
    ri = get_random_index(n)
    cr = ci / ri if ri != 0 else 0
    
    return {
        'weights': weights,
        'lambda_max': max_eigenvalue,
        'ci': ci,
        'ri': ri,
        'cr': cr,
        'normalized_matrix': matrix / matrix.sum(axis=0),
        'weighted_sum': np.dot(matrix, weights),
        'consistency_vector': np.dot(matrix, weights) / weights
    }

def get_random_index(n):
    """Mengembalikan Random Index berdasarkan ukuran matriks"""
    ri_table = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.9, 5: 1.12,
                6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
    return ri_table.get(n, 1.5)

def get_kriteria_weights():
    """Menghitung bobot kriteria"""
    kriteria = get_data("kriteria")
    n = len(kriteria)
    
    if n == 0:
        return {}, 0.0
    
    perbandingan = get_data("perbandingan_kriteria")
    matrix = np.ones((n, n))
    
    for p in perbandingan:
        i = p['id_kriteria1'] - 1
        j = p['id_kriteria2'] - 1
        matrix[i, j] = p['nilai_perbandingan']
        matrix[j, i] = 1 / p['nilai_perbandingan']
    
    result = calculate_ahp(matrix)
    weights = {kriteria[i]['id_kriteria']: result['weights'][i] for i in range(n)}
    
    return weights, result['cr']

def get_subkriteria_weights():
    """Menghitung bobot subkriteria untuk semua kriteria"""
    kriteria = get_data("kriteria")
    subkriteria_weights = {}
    cr_results = {}
    
    for k in kriteria:
        subkriteria = get_data("subkriteria", where=f"id_kriteria={k['id_kriteria']}")
        n = len(subkriteria)
        
        if n < 2:
            continue
            
        perbandingan = get_data("perbandingan_subkriteria", where=f"id_kriteria={k['id_kriteria']}")
        
        matrix = np.ones((n, n))
        for p in perbandingan:
            i = p['id_subkriteria1'] - min(sub['id_subkriteria'] for sub in subkriteria)
            j = p['id_subkriteria2'] - min(sub['id_subkriteria'] for sub in subkriteria)
            matrix[i, j] = p['nilai_perbandingan']
            matrix[j, i] = 1 / p['nilai_perbandingan']
        
        result = calculate_ahp(matrix)
        subkriteria_weights[k['id_kriteria']] = {
            'weights': {subkriteria[i]['id_subkriteria']: result['weights'][i] for i in range(n)},
            'cr': result['cr'],
            'matrix': matrix,
            'subkriteria': subkriteria
        }
        cr_results[k['id_kriteria']] = result['cr']
    
    return subkriteria_weights, cr_results
# Fungsi perhitungan lainnya...

def get_perbandingan_subkriteria(id_kriteria):
    """Mengambil perbandingan subkriteria berdasarkan kriteria"""
    return get_data(
        "perbandingan_subkriteria", 
        where=f"id_kriteria={id_kriteria}"
    )

def save_perbandingan_subkriteria(id_kriteria, id_subkriteria1, id_subkriteria2, nilai):
    """Menyimpan/mengupdate perbandingan subkriteria"""
    conn = create_connection()
    if conn is None:
        return False
    
    try:
        cursor = conn.cursor()
        # Cek apakah data sudah ada
        cursor.execute(
            """SELECT 1 FROM perbandingan_subkriteria 
            WHERE id_kriteria=%s AND (
                (id_subkriteria1=%s AND id_subkriteria2=%s)
                OR (id_subkriteria1=%s AND id_subkriteria2=%s)
            )""",
            (id_kriteria, id_subkriteria1, id_subkriteria2, id_subkriteria2, id_subkriteria1)
        )
        exists = cursor.fetchone()
        
        if exists:
            # Update jika sudah ada
            cursor.execute(
                """UPDATE perbandingan_subkriteria SET nilai_perbandingan=%s
                WHERE id_kriteria=%s AND id_subkriteria1=%s AND id_subkriteria2=%s""",
                (nilai, id_kriteria, id_subkriteria1, id_subkriteria2)
            )
        else:
            # Tambah baru jika belum ada
            cursor.execute(
                """INSERT INTO perbandingan_subkriteria 
                (id_kriteria, id_subkriteria1, id_subkriteria2, nilai_perbandingan)
                VALUES (%s, %s, %s, %s)""",
                (id_kriteria, id_subkriteria1, id_subkriteria2, nilai)
            )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Gagal menyimpan perbandingan subkriteria: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def delete_perbandingan_subkriteria(id_kriteria, id_subkriteria1, id_subkriteria2):
    """Menghapus perbandingan subkriteria"""
    conn = create_connection()
    if conn is None:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            """DELETE FROM perbandingan_subkriteria 
            WHERE id_kriteria=%s AND (
                (id_subkriteria1=%s AND id_subkriteria2=%s)
                OR (id_subkriteria1=%s AND id_subkriteria2=%s)
            )""",
            (id_kriteria, id_subkriteria1, id_subkriteria2, id_subkriteria2, id_subkriteria1)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Gagal menghapus perbandingan subkriteria: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()
def display_comparison_matrix(items, comparisons, item_type):
    """Menampilkan matriks perbandingan dalam tabel"""
    n = len(items)
    matrix = np.ones((n, n))
    item_ids = [item[f"id_{item_type}"] for item in items]
    item_names = [item[f"nama_{item_type}"] for item in items]
    
    for comp in comparisons:
        i = item_ids.index(comp[f"id_{item_type}1"])
        j = item_ids.index(comp[f"id_{item_type}2"])
        matrix[i, j] = comp["nilai_perbandingan"]
        matrix[j, i] = 1 / comp["nilai_perbandingan"]
    
    df = pd.DataFrame(matrix, index=item_names, columns=item_names)
    st.dataframe(df.style.format("{:.3f}"), use_container_width=True)
def calculate_ranking():
    """
    Menghitung perankingan guru berdasarkan:
    - Bobot kriteria
    - Bobot subkriteria
    - Nilai subkriteria setiap guru
    Return:
        DataFrame hasil perankingan
        CR kriteria
        CR subkriteria
    """
    from database import get_data
    
    # 1. Hitung bobot kriteria
    kriteria_weights, kriteria_cr = get_kriteria_weights()
    if not kriteria_weights:
        return None, None, None
    
    # 2. Hitung bobot subkriteria
    subkriteria_weights, subkriteria_cr = get_subkriteria_weights()
    
    # 3. Dapatkan data guru dan nilai
    guru_list = get_data("guru")
    nilai_subkriteria = get_data("nilai_subkriteria")
    
    results = []
    
    for guru in guru_list:
        total_score = 0
        detail_scores = {}
        
        for id_kriteria, kriteria_weight in kriteria_weights.items():
            kriteria_score = 0
            
            # Jika ada subkriteria
            if id_kriteria in subkriteria_weights:
                for id_sub, sub_weight in subkriteria_weights[id_kriteria]['weights'].items():
                    # Cari nilai subkriteria guru ini
                    nilai = next(
                        (ns['nilai'] for ns in nilai_subkriteria 
                         if ns['id_guru'] == guru['id_guru'] and ns['id_subkriteria'] == id_sub),
                        0  # Default nilai 0 jika tidak ada
                    )
                    kriteria_score += nilai * sub_weight
            
            total_score += kriteria_score * kriteria_weight
            detail_scores[f"Kriteria {id_kriteria}"] = kriteria_score * kriteria_weight
        
        results.append({
            'id_guru': guru['id_guru'],
            'nama_guru': guru['nama_guru'],
            'nip': guru['nip'],
            'total_score': total_score,
            **detail_scores  # Unpack detail scores
        })
    
    # Urutkan berdasarkan total score
    ranked_results = sorted(results, key=lambda x: x['total_score'], reverse=True)
    
    # Konversi ke DataFrame
    df_results = pd.DataFrame(ranked_results)
    
    # Hitung peringkat
    df_results['Peringkat'] = df_results['total_score'].rank(ascending=False, method='min').astype(int)
    
    return df_results, kriteria_cr, subkriteria_cr