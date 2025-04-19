# utils/stats_utils.py
import pandas as pd
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
import seaborn as sns  # Import library seaborn
import tempfile
from database import create_connection

def calculate_spearman_rank(guru_id=None, start_date=None, end_date=None):
    """
    Menghitung korelasi rank Spearman antar subkriteria
    
    Parameters:
        guru_id: ID guru tertentu (None untuk semua guru)
        start_date: Tanggal awal (None untuk tidak dibatasi)
        end_date: Tanggal akhir (None untuk tidak dibatasi)
    
    Returns:
        Tuple: (correlation_matrix, p_value_matrix, plot_path)
    """
    conn = None
    try:
        # Dapatkan data dari database
        conn = create_connection()
        query = """
        SELECT n.id_guru, n.id_subkriteria, s.nama_subkriteria, n.nilai, n.tanggal_penilaian
        FROM nilai_subkriteria n
        JOIN subkriteria s ON n.id_subkriteria = s.id_subkriteria
        """
        
        conditions = []
        if guru_id:
            conditions.append(f"n.id_guru = {guru_id}")
        if start_date:
            conditions.append(f"n.tanggal_penilaian >= '{start_date}'")
        if end_date:
            conditions.append(f"n.tanggal_penilaian <= '{end_date}'")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY n.id_guru, n.tanggal_penilaian"
        
        df = pd.read_sql(query, conn)
        
        if df.empty:
            return None, None, None
        
        # Pivot data untuk korelasi
        pivot_df = df.pivot_table(
            index=['id_guru', 'tanggal_penilaian'],
            columns='nama_subkriteria',
            values='nilai',
            aggfunc='mean'
        ).reset_index()
        
        # Hitung korelasi Spearman
        corr_matrix, p_matrix = stats.spearmanr(
            pivot_df.select_dtypes(include=[np.number]), 
            nan_policy='omit'
        )
        
        # Buat visualisasi
        plt.figure(figsize=(12, 8))
        subkriteria_names = pivot_df.select_dtypes(include=[np.number]).columns.tolist()
        
        # Buat mask untuk segitiga atas
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
        
        sns.heatmap(
            corr_matrix,
            mask=mask,
            annot=True,
            fmt=".2f",
            cmap="coolwarm",
            center=0,
            xticklabels=subkriteria_names,
            yticklabels=subkriteria_names,
            vmin=-1,
            vmax=1
        )
        plt.title("Korelasi Rank Spearman Antar Subkriteria", pad=20)
        plt.xticks(rotation=45, ha='right')
        plt.yticks(rotation=0)
        
        # Simpan plot ke file temporer
        plot_path = tempfile.mktemp(suffix='.png')
        plt.savefig(plot_path, bbox_inches='tight', dpi=300)
        plt.close()
        
        return corr_matrix, p_matrix, plot_path
        
    except Exception as e:
        print(f"Error in spearman calculation: {str(e)}")
        return None, None, None
    finally:
        if conn:
            conn.close()
        plt.close('all')