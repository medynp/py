import pandas as pd
from datetime import datetime

def import_guru_data(uploaded_file):
    """Mengimpor data guru dari file Excel"""
    try:
        df = pd.read_excel(uploaded_file, engine='openpyxl')
        
        # Validasi
        required_cols = ['nama_guru', 'nip']
        if not all(col in df.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df.columns]
            raise ValueError(f"Kolom wajib tidak ditemukan: {missing}")
        
        # Konversi data
        data_list = []
        for _, row in df.iterrows():
            data = {
                'nama_guru': str(row['nama_guru']),
                'nip': str(row['nip']),
                'jabatan': str(row.get('jabatan', '')),
                'tanggal_masuk': pd.to_datetime(row['tanggal_masuk']).date() if 'tanggal_masuk' in df.columns and pd.notna(row['tanggal_masuk']) else None
            }
            data_list.append(data)
            
        return data_list
        
    except Exception as e:
        raise Exception(f"Error import data: {str(e)}")
    
def import_nilai_data(uploaded_file, guru_list, subkriteria_list):
    """Mengimpor data nilai dari Excel"""
    try:
        df = pd.read_excel(uploaded_file, engine='openpyxl')
        
        # Validasi
        if 'nip' not in df.columns:
            raise ValueError("Kolom 'nip' tidak ditemukan")
            
        # Mapping data
        subkriteria_map = {sub['nama_subkriteria']: sub['id_subkriteria'] for sub in subkriteria_list}
        guru_map = {g['nip']: g['id_guru'] for g in guru_list}
        
        data_list = []
        for _, row in df.iterrows():
            nip = str(row['nip'])
            if nip not in guru_map:
                continue
                
            for col in df.columns:
                if col in subkriteria_map:
                    nilai = int(row[col])
                    if 1 <= nilai <= 5:
                        data_list.append({
                            'id_guru': guru_map[nip],
                            'id_subkriteria': subkriteria_map[col],
                            'nilai': nilai,
                            'tanggal_penilaian': pd.to_datetime(row['tanggal_penilaian']).date() if 'tanggal_penilaian' in df.columns else datetime.now().date()
                        })
        
        return data_list
        
    except Exception as e:
        raise Exception(f"Error import nilai: {str(e)}")