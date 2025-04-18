import streamlit as st
import mysql.connector
import numpy as np
import pandas as pd
from datetime import datetime

# Fungsi untuk koneksi database
def create_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="sistem_ahp_guru"
    )

# Fungsi untuk mendapatkan data dari database
def get_data(table_name, columns="*", where=""):
    conn = create_connection()
    cursor = conn.cursor(dictionary=True)
    query = f"SELECT {columns} FROM {table_name}"
    if where:
        query += f" WHERE {where}"
    cursor.execute(query)
    result = cursor.fetchall()
    conn.close()
    return result

# Fungsi untuk menyimpan data ke database
def save_data(table_name, data):
    conn = create_connection()
    cursor = conn.cursor()
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["%s"] * len(data))
    query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
    cursor.execute(query, tuple(data.values()))
    conn.commit()
    conn.close()
    return cursor.lastrowid

# Fungsi untuk update data
def update_data(table_name, data, where):
    conn = create_connection()
    cursor = conn.cursor()
    set_clause = ", ".join([f"{key}=%s" for key in data.keys()])
    query = f"UPDATE {table_name} SET {set_clause} WHERE {where}"
    cursor.execute(query, tuple(data.values()))
    conn.commit()
    conn.close()

# Fungsi untuk menghitung matriks perbandingan AHP
def calculate_ahp(matrix):
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

# Fungsi untuk memeriksa konsistensi matriks
def check_consistency(cr):
    if cr < 0.1:
        return "Konsisten (CR < 0.1)"
    else:
        return "Tidak Konsisten (CR ≥ 0.1). Silakan periksa kembali perbandingan."

# Fungsi untuk mendapatkan bobot kriteria
def get_kriteria_weights():
    kriteria = get_data("kriteria")
    n = len(kriteria)
    
    # Ambil data perbandingan kriteria dari database
    perbandingan = get_data("perbandingan_kriteria")
    
    # Buat matriks perbandingan
    matrix = np.ones((n, n))
    for p in perbandingan:
        i = p['id_kriteria1'] - 1
        j = p['id_kriteria2'] - 1
        matrix[i, j] = p['nilai_perbandingan']
        matrix[j, i] = 1 / p['nilai_perbandingan']
    
    # Hitung bobot kriteria
    weights, cr = calculate_ahp(matrix)
    
    return {kriteria[i]['id_kriteria']: weights[i] for i in range(n)}, cr

# Fungsi untuk mendapatkan bobot subkriteria per kriteria
def get_subkriteria_weights():
    kriteria = get_data("kriteria")
    subkriteria_weights = {}
    cr_dict = {}
    
    for k in kriteria:
        subkriteria = get_data("subkriteria", where=f"id_kriteria={k['id_kriteria']}")
        n = len(subkriteria)
        
        if n == 0:
            continue
            
        # Ambil data perbandingan subkriteria dari database
        perbandingan = get_data("perbandingan_subkriteria", where=f"id_kriteria={k['id_kriteria']}")
        
        # Buat matriks perbandingan
        matrix = np.ones((n, n))
        for p in perbandingan:
            i = p['id_subkriteria1'] - min(sub['id_subkriteria'] for sub in subkriteria)
            j = p['id_subkriteria2'] - min(sub['id_subkriteria'] for sub in subkriteria)
            matrix[i, j] = p['nilai_perbandingan']
            matrix[j, i] = 1 / p['nilai_perbandingan']
        
        # Hitung bobot subkriteria
        weights, cr = calculate_ahp(matrix)
        
        # Simpan bobot subkriteria
        subkriteria_weights[k['id_kriteria']] = {
            subkriteria[i]['id_subkriteria']: weights[i] for i in range(n)
        }
        cr_dict[k['id_kriteria']] = cr
    
    return subkriteria_weights, cr_dict

# Fungsi untuk menghitung nilai total AHP
def calculate_total_scores():
    # Dapatkan bobot kriteria
    kriteria_weights, kriteria_cr = get_kriteria_weights()
    
    # Dapatkan bobot subkriteria
    subkriteria_weights, subkriteria_cr = get_subkriteria_weights()
    
    # Dapatkan semua guru
    guru_list = get_data("guru")
    
    # Dapatkan semua nilai subkriteria
    nilai_subkriteria = get_data("nilai_subkriteria")
    
    # Hitung nilai total untuk setiap guru
    results = []
    for guru in guru_list:
        total_score = 0
        detail_scores = {}
        
        # Hitung nilai untuk setiap kriteria
        for id_kriteria, kriteria_weight in kriteria_weights.items():
            # Dapatkan subkriteria untuk kriteria ini
            subs = subkriteria_weights.get(id_kriteria, {})
            kriteria_score = 0
            
            # Hitung nilai subkriteria
            for id_sub, sub_weight in subs.items():
                # Cari nilai subkriteria untuk guru ini
                nilai = next((ns['nilai'] for ns in nilai_subkriteria 
                            if ns['id_guru'] == guru['id_guru'] and ns['id_subkriteria'] == id_sub), 0)
                
                # Tambahkan ke skor kriteria
                kriteria_score += nilai * sub_weight
            
            # Tambahkan ke skor total dengan bobot kriteria
            total_score += kriteria_score * kriteria_weight
            detail_scores[f"Kriteria {id_kriteria}"] = kriteria_score * kriteria_weight
        
        results.append({
            'id_guru': guru['id_guru'],
            'nama_guru': guru['nama_guru'],
            'nip': guru['nip'],
            'total_score': total_score,
            'detail_scores': detail_scores
        })
    
    return sorted(results, key=lambda x: x['total_score'], reverse=True), kriteria_cr, subkriteria_cr

# Fungsi utama aplikasi
def main():
    st.title("Sistem AHP untuk Penilaian Kenaikan Status Guru")
    
    menu = st.sidebar.selectbox("Menu", [
        "Dashboard", 
        "Manajemen Guru", 
        "Manajemen Kriteria & Subkriteria",
        "Perbandingan Kriteria & Subkriteria",
        "Penilaian Guru",
        "Hasil Perangkingan"
    ])
    
    if menu == "Dashboard":
        st.header("Dashboard")
        st.write("Selamat datang di Sistem AHP untuk Penilaian Kenaikan Status Guru")
        
        # Statistik singkat
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Jumlah Guru", len(get_data("guru")))
        with col2:
            st.metric("Jumlah Kriteria", len(get_data("kriteria")))
        with col3:
            st.metric("Jumlah Subkriteria", len(get_data("subkriteria")))
        
    elif menu == "Manajemen Guru":
        st.header("Manajemen Data Guru")
        
        tab1, tab2 = st.tabs(["Daftar Guru", "Tambah Guru"])
        
        with tab1:
            st.subheader("Daftar Guru")
            guru_list = get_data("guru")
            if guru_list:
                df = pd.DataFrame(guru_list)
                st.dataframe(df)
            else:
                st.warning("Belum ada data guru")
        
        with tab2:
            st.subheader("Tambah Guru Baru")
            with st.form("form_tambah_guru"):
                nama = st.text_input("Nama Guru")
                nip = st.text_input("NIP")
                jabatan = st.text_input("Jabatan")
                tgl_masuk = st.date_input("Tanggal Masuk")
                
                submitted = st.form_submit_button("Simpan")
                if submitted:
                    if nama and nip:
                        data = {
                            'nama_guru': nama,
                            'nip': nip,
                            'jabatan': jabatan,
                            'tanggal_masuk': tgl_masuk
                        }
                        save_data("guru", data)
                        st.success("Data guru berhasil disimpan")
                    else:
                        st.error("Nama dan NIP wajib diisi")
    
    elif menu == "Manajemen Kriteria & Subkriteria":
        st.header("Manajemen Kriteria & Subkriteria")
        
        tab1, tab2, tab3 = st.tabs(["Kriteria", "Tambah Kriteria", "Subkriteria"])
        
        with tab1:
            st.subheader("Daftar Kriteria")
            kriteria_list = get_data("kriteria")
            if kriteria_list:
                df = pd.DataFrame(kriteria_list)
                st.dataframe(df)
            else:
                st.warning("Belum ada data kriteria")
        
        with tab2:
            st.subheader("Tambah Kriteria Baru")
            with st.form("form_tambah_kriteria"):
                nama = st.text_input("Nama Kriteria")
                deskripsi = st.text_area("Deskripsi")
                
                submitted = st.form_submit_button("Simpan")
                if submitted:
                    if nama:
                        data = {
                            'nama_kriteria': nama,
                            'deskripsi': deskripsi
                        }
                        save_data("kriteria", data)
                        st.success("Data kriteria berhasil disimpan")
                    else:
                        st.error("Nama kriteria wajib diisi")
        
        with tab3:
            st.subheader("Manajemen Subkriteria")
            kriteria_list = get_data("kriteria")
            if not kriteria_list:
                st.warning("Belum ada data kriteria. Silakan tambah kriteria terlebih dahulu.")
            else:
                selected_kriteria = st.selectbox(
                    "Pilih Kriteria",
                    kriteria_list,
                    format_func=lambda x: x['nama_kriteria']
                )
                
                # Daftar subkriteria untuk kriteria terpilih
                st.write(f"Daftar Subkriteria untuk {selected_kriteria['nama_kriteria']}")
                subkriteria_list = get_data("subkriteria", where=f"id_kriteria={selected_kriteria['id_kriteria']}")
                if subkriteria_list:
                    df = pd.DataFrame(subkriteria_list)
                    st.dataframe(df)
                else:
                    st.warning(f"Belum ada subkriteria untuk {selected_kriteria['nama_kriteria']}")
                
                # Form tambah subkriteria
                with st.form("form_tambah_subkriteria"):
                    nama_sub = st.text_input("Nama Subkriteria")
                    deskripsi_sub = st.text_area("Deskripsi Subkriteria")
                    
                    submitted = st.form_submit_button("Tambah Subkriteria")
                    if submitted:
                        if nama_sub:
                            data = {
                                'id_kriteria': selected_kriteria['id_kriteria'],
                                'nama_subkriteria': nama_sub,
                                'deskripsi': deskripsi_sub
                            }
                            save_data("subkriteria", data)
                            st.success("Subkriteria berhasil ditambahkan")
                        else:
                            st.error("Nama subkriteria wajib diisi")
    
    elif menu == "Perbandingan Kriteria & Subkriteria":
        st.header("Perbandingan Kriteria & Subkriteria")
        
        tab1, tab2 = st.tabs(["Perbandingan Kriteria", "Perbandingan Subkriteria"])
        
        with tab1:
            st.subheader("Perbandingan Kriteria (Pairwise Comparison)")
            kriteria_list = get_data("kriteria")
            
            if len(kriteria_list) < 2:
                st.warning("Minimal harus ada 2 kriteria untuk melakukan perbandingan")
            else:
                # Cek apakah sudah ada data perbandingan
                existing_comparisons = get_data("perbandingan_kriteria")
                
                if existing_comparisons:
                    st.info("Data perbandingan kriteria sudah ada. Anda dapat memperbarui jika diperlukan.")
                
                # Buat matriks perbandingan
                st.write("**Matriks Perbandingan Kriteria**")
                st.write("Silakan isi nilai perbandingan antara kriteria (1-9 atau 1/9-1/1)")
                
                # Buat form untuk input perbandingan
                with st.form("form_perbandingan_kriteria"):
                    comparisons = {}
                    
                    # Buat input untuk setiap pasangan kriteria
                    for i in range(len(kriteria_list)):
                        for j in range(i+1, len(kriteria_list)):
                            krit1 = kriteria_list[i]
                            krit2 = kriteria_list[j]
                            
                            # Cari nilai perbandingan yang sudah ada
                            existing_value = None
                            for comp in existing_comparisons:
                                if (comp['id_kriteria1'] == krit1['id_kriteria'] and 
                                    comp['id_kriteria2'] == krit2['id_kriteria']):
                                    existing_value = comp['nilai_perbandingan']
                                    break
                                elif (comp['id_kriteria1'] == krit2['id_kriteria'] and 
                                      comp['id_kriteria2'] == krit1['id_kriteria']):
                                    existing_value = 1 / comp['nilai_perbandingan']
                                    break
                            
                            # Buat slider untuk input nilai
                            key = f"{krit1['id_kriteria']}_{krit2['id_kriteria']}"
                            label = f"{krit1['nama_kriteria']} vs {krit2['nama_kriteria']}"
                            
                            min_val, max_val = 1/9, 9
                            step = 0.5
                            scale = np.concatenate([
                                np.arange(1/9, 1, step),
                                np.arange(1, 10, step)
                            ])
                            
                            comparisons[key] = st.select_slider(
                                label,
                                options=scale,
                                value=existing_value if existing_value else 1.0,
                                format_func=lambda x: f"{x:.2f}" if x < 1 else f"{x:.0f}"
                            )
                    
                    submitted = st.form_submit_button("Simpan Perbandingan")
                    if submitted:
                        # Hapus semua perbandingan yang ada
                        conn = create_connection()
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM perbandingan_kriteria")
                        conn.commit()
                        
                        # Simpan perbandingan baru
                        for key, value in comparisons.items():
                            id1, id2 = map(int, key.split('_'))
                            if value >= 1:
                                data = {
                                    'id_kriteria1': id1,
                                    'id_kriteria2': id2,
                                    'nilai_perbandingan': value
                                }
                            else:
                                data = {
                                    'id_kriteria1': id2,
                                    'id_kriteria2': id1,
                                    'nilai_perbandingan': 1/value
                                }
                            save_data("perbandingan_kriteria", data)
                        
                        st.success("Data perbandingan kriteria berhasil disimpan")
                        
                        # Hitung dan tampilkan bobot kriteria
                        weights, cr = get_kriteria_weights()
                        st.subheader("Hasil Perhitungan Bobot Kriteria")
                        
                        df_weights = pd.DataFrame([
                            {
                                'Kriteria': k['nama_kriteria'],
                                'Bobot': weights[k['id_kriteria']]
                            }
                            for k in kriteria_list
                        ])
                        st.dataframe(df_weights)
                        
                        st.subheader("Konsistensi Perbandingan")
                        st.write(f"Consistency Ratio (CR): {cr:.4f}")
                        st.write(check_consistency(cr))
        
        with tab2:
            st.subheader("Perbandingan Subkriteria (Pairwise Comparison)")
            kriteria_list = get_data("kriteria")
            
            selected_kriteria = st.selectbox(
                "Pilih Kriteria",
                kriteria_list,
                format_func=lambda x: x['nama_kriteria']
            )
            
            subkriteria_list = get_data("subkriteria", where=f"id_kriteria={selected_kriteria['id_kriteria']}")
            
            if len(subkriteria_list) < 2:
                st.warning(f"Minimal harus ada 2 subkriteria untuk {selected_kriteria['nama_kriteria']} untuk melakukan perbandingan")
            else:
                # Cek apakah sudah ada data perbandingan
                existing_comparisons = get_data(
                    "perbandingan_subkriteria", 
                    where=f"id_kriteria={selected_kriteria['id_kriteria']}"
                )
                
                if existing_comparisons:
                    st.info(f"Data perbandingan subkriteria untuk {selected_kriteria['nama_kriteria']} sudah ada. Anda dapat memperbarui jika diperlukan.")
                
                # Buat matriks perbandingan
                st.write(f"**Matriks Perbandingan Subkriteria untuk {selected_kriteria['nama_kriteria']}**")
                st.write("Silakan isi nilai perbandingan antara subkriteria (1-9 atau 1/9-1/1)")
                
                # Buat form untuk input perbandingan
                with st.form("form_perbandingan_subkriteria"):
                    comparisons = {}
                    
                    # Buat input untuk setiap pasangan subkriteria
                    for i in range(len(subkriteria_list)):
                        for j in range(i+1, len(subkriteria_list)):
                            sub1 = subkriteria_list[i]
                            sub2 = subkriteria_list[j]
                            
                            # Cari nilai perbandingan yang sudah ada
                            existing_value = None
                            for comp in existing_comparisons:
                                if (comp['id_subkriteria1'] == sub1['id_subkriteria'] and 
                                    comp['id_subkriteria2'] == sub2['id_subkriteria']):
                                    existing_value = comp['nilai_perbandingan']
                                    break
                                elif (comp['id_subkriteria1'] == sub2['id_subkriteria'] and 
                                      comp['id_subkriteria2'] == sub1['id_subkriteria']):
                                    existing_value = 1 / comp['nilai_perbandingan']
                                    break
                            
                            # Buat slider untuk input nilai
                            key = f"{sub1['id_subkriteria']}_{sub2['id_subkriteria']}"
                            label = f"{sub1['nama_subkriteria']} vs {sub2['nama_subkriteria']}"
                            
                            min_val, max_val = 1/9, 9
                            step = 0.5
                            scale = np.concatenate([
                                np.arange(1/9, 1, step),
                                np.arange(1, 10, step)
                            ])
                            
                            comparisons[key] = st.select_slider(
                                label,
                                options=scale,
                                value=existing_value if existing_value else 1.0,
                                format_func=lambda x: f"{x:.2f}" if x < 1 else f"{x:.0f}"
                            )
                    
                    submitted = st.form_submit_button("Simpan Perbandingan Subkriteria")
                    if submitted:
                        # Hapus semua perbandingan yang ada untuk kriteria ini
                        conn = create_connection()
                        cursor = conn.cursor()
                        cursor.execute(
                            "DELETE FROM perbandingan_subkriteria WHERE id_kriteria=%s",
                            (selected_kriteria['id_kriteria'],)
                        )
                        conn.commit()
                        
                        # Simpan perbandingan baru
                        for key, value in comparisons.items():
                            id1, id2 = map(int, key.split('_'))
                            if value >= 1:
                                data = {
                                    'id_kriteria': selected_kriteria['id_kriteria'],
                                    'id_subkriteria1': id1,
                                    'id_subkriteria2': id2,
                                    'nilai_perbandingan': value
                                }
                            else:
                                data = {
                                    'id_kriteria': selected_kriteria['id_kriteria'],
                                    'id_subkriteria1': id2,
                                    'id_subkriteria2': id1,
                                    'nilai_perbandingan': 1/value
                                }
                            save_data("perbandingan_subkriteria", data)
                        
                        st.success(f"Data perbandingan subkriteria untuk {selected_kriteria['nama_kriteria']} berhasil disimpan")
                        
                        # Hitung dan tampilkan bobot subkriteria
                        subkriteria_weights, cr_dict = get_subkriteria_weights()
                        weights = subkriteria_weights.get(selected_kriteria['id_kriteria'], {})
                        
                        if weights:
                            st.subheader(f"Hasil Perhitungan Bobot Subkriteria untuk {selected_kriteria['nama_kriteria']}")
                            
                            df_weights = pd.DataFrame([
                                {
                                    'Subkriteria': next(sub['nama_subkriteria'] for sub in subkriteria_list if sub['id_subkriteria'] == sub_id),
                                    'Bobot': weight
                                }
                                for sub_id, weight in weights.items()
                            ])
                            st.dataframe(df_weights)
                            
                            cr = cr_dict.get(selected_kriteria['id_kriteria'], 0)
                            st.subheader("Konsistensi Perbandingan")
                            st.write(f"Consistency Ratio (CR): {cr:.4f}")
                            st.write(check_consistency(cr))
    
    elif menu == "Penilaian Guru":
        st.header("Penilaian Guru Berdasarkan Subkriteria")
        
        # Pilih guru
        guru_list = get_data("guru")
        selected_guru = st.selectbox(
            "Pilih Guru",
            guru_list,
            format_func=lambda x: f"{x['nama_guru']} ({x['nip']})"
        )
        
        # Daftar kriteria dan subkriteria
        kriteria_list = get_data("kriteria")
        
        if not kriteria_list:
            st.warning("Belum ada kriteria yang ditentukan")
        else:
            with st.form("form_penilaian_guru"):
                nilai_subkriteria = {}
                
                for kriteria in kriteria_list:
                    st.subheader(f"Kriteria: {kriteria['nama_kriteria']}")
                    
                    # Dapatkan subkriteria untuk kriteria ini
                    subkriteria_list = get_data(
                        "subkriteria", 
                        where=f"id_kriteria={kriteria['id_kriteria']}"
                    )
                    
                    if not subkriteria_list:
                        st.warning(f"Belum ada subkriteria untuk {kriteria['nama_kriteria']}")
                        continue
                    
                    for sub in subkriteria_list:
                        # Cek apakah sudah ada nilai sebelumnya
                        existing_nilai = get_data(
                            "nilai_subkriteria",
                            where=f"id_guru={selected_guru['id_guru']} AND id_subkriteria={sub['id_subkriteria']}"
                        )
                        
                        nilai = st.number_input(
                            f"Nilai untuk {sub['nama_subkriteria']} (1-100)",
                            min_value=0,
                            max_value=100,
                            value=existing_nilai[0]['nilai'] if existing_nilai else 50,
                            key=f"nilai_{sub['id_subkriteria']}"
                        )
                        nilai_subkriteria[sub['id_subkriteria']] = nilai
                
                submitted = st.form_submit_button("Simpan Penilaian")
                if submitted:
                    # Simpan nilai subkriteria
                    for sub_id, nilai in nilai_subkriteria.items():
                        # Cek apakah sudah ada nilai untuk guru dan subkriteria ini
                        existing = get_data(
                            "nilai_subkriteria",
                            where=f"id_guru={selected_guru['id_guru']} AND id_subkriteria={sub_id}"
                        )
                        
                        if existing:
                            # Update nilai yang sudah ada
                            update_data(
                                "nilai_subkriteria",
                                {'nilai': nilai, 'tanggal_penilaian': datetime.now().date()},
                                f"id_nilai={existing[0]['id_nilai']}"
                            )
                        else:
                            # Tambah nilai baru
                            data = {
                                'id_guru': selected_guru['id_guru'],
                                'id_subkriteria': sub_id,
                                'nilai': nilai,
                                'tanggal_penilaian': datetime.now().date()
                            }
                            save_data("nilai_subkriteria", data)
                    
                    st.success("Penilaian berhasil disimpan")
    
    elif menu == "Hasil Perangkingan":
        st.header("Hasil Perangkingan Guru")
        
        if st.button("Hitung Ulang Perangkingan"):
            with st.spinner("Menghitung perangkingan..."):
                results, kriteria_cr, subkriteria_cr = calculate_total_scores()
                
                # Simpan hasil ke database
                conn = create_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM hasil_ahp")
                conn.commit()
                
                for result in results:
                    data = {
                        'id_guru': result['id_guru'],
                        'total_nilai': result['total_score'],
                        'tanggal_hitung': datetime.now()
                    }
                    save_data("hasil_ahp", data)
                
                st.success("Perhitungan perangkingan selesai")
        
        # Tampilkan hasil perangkingan
        st.subheader("Daftar Perangkingan Guru")
        
        results_db = get_data("hasil_ahp", "id_guru, total_nilai, tanggal_hitung")
        guru_list = get_data("guru")
        
        if not results_db:
            st.warning("Belum ada hasil perangkingan. Silakan klik tombol 'Hitung Ulang Perangkingan'")
        else:
            # Gabungkan data guru dengan hasil perhitungan
            ranked_results = []
            for res in sorted(results_db, key=lambda x: x['total_nilai'], reverse=True):
                guru = next((g for g in guru_list if g['id_guru'] == res['id_guru']), None)
                if guru:
                    ranked_results.append({
                        'Peringkat': len(ranked_results) + 1,
                        'Nama Guru': guru['nama_guru'],
                        'NIP': guru['nip'],
                        'Total Nilai': res['total_nilai'],
                        'Terakhir Diupdate': res['tanggal_hitung']
                    })
            
            df = pd.DataFrame(ranked_results)
            st.dataframe(df)
            
            # Tampilkan detail konsistensi
            st.subheader("Informasi Konsistensi")
            
            # Kriteria
            kriteria_weights, kriteria_cr = get_kriteria_weights()
            st.write(f"**Kriteria** - Consistency Ratio (CR): {kriteria_cr:.4f}")
            st.write(check_consistency(kriteria_cr))
            
            # Subkriteria
            subkriteria_weights, subkriteria_cr = get_subkriteria_weights()
            st.write("**Subkriteria**")
            for id_kriteria, cr in subkriteria_cr.items():
                kriteria = next(k for k in get_data("kriteria") if k['id_kriteria'] == id_kriteria)
                st.write(f"- {kriteria['nama_kriteria']}: CR = {cr:.4f} ({check_consistency(cr)})")

if __name__ == "__main__":
    main()