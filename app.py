import streamlit as st
import numpy as np
import pandas as pd
from datetime import datetime
from database import create_connection, init_database, bulk_insert, get_data
from ahp_calculations import calculate_ahp, check_consistency
from utils.template_utils import download_guru_template, download_nilai_template
from utils.import_utils import import_guru_data, import_nilai_data


# Inisialisasi database
init_database()

# Fungsi-fungsi database
def get_data(table_name, columns="*", where=""):
    conn = create_connection()
    if conn is None:
        return []
    
    cursor = conn.cursor(dictionary=True)
    query = f"SELECT {columns} FROM {table_name}"
    if where:
        query += f" WHERE {where}"
    
    try:
        cursor.execute(query)
        result = cursor.fetchall()
        return result
    except Exception as e:
        st.error(f"Error mendapatkan data: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def save_data(table_name, data):
    conn = create_connection()
    if conn is None:
        return None
    
    cursor = conn.cursor()
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["%s"] * len(data))
    query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
    
    try:
        cursor.execute(query, tuple(data.values()))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        st.error(f"Error menyimpan data: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def update_data(table_name, data, where):
    conn = create_connection()
    if conn is None:
        return False
    
    cursor = conn.cursor()
    set_clause = ", ".join([f"{key}=%s" for key in data.keys()])
    query = f"UPDATE {table_name} SET {set_clause} WHERE {where}"
    
    try:
        cursor.execute(query, tuple(data.values()))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error mengupdate data: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

# Fungsi-fungsi khusus AHP
def get_kriteria_weights():
    kriteria = get_data("kriteria")
    n = len(kriteria)
    
    if n == 0:
        return {}, 0
    
    perbandingan = get_data("perbandingan_kriteria")
    
    matrix = np.ones((n, n))
    for p in perbandingan:
        i = p['id_kriteria1'] - 1
        j = p['id_kriteria2'] - 1
        matrix[i, j] = p['nilai_perbandingan']
        matrix[j, i] = 1 / p['nilai_perbandingan']
    
    weights, cr = calculate_ahp(matrix)
    return {kriteria[i]['id_kriteria']: weights[i] for i in range(n)}, cr

def get_subkriteria_weights():
    kriteria = get_data("kriteria")
    subkriteria_weights = {}
    cr_dict = {}
    
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
        
        weights, cr = calculate_ahp(matrix)
        subkriteria_weights[k['id_kriteria']] = {
            subkriteria[i]['id_subkriteria']: weights[i] for i in range(n)
        }
        cr_dict[k['id_kriteria']] = cr
    
    return subkriteria_weights, cr_dict

def calculate_total_scores():
    kriteria_weights, kriteria_cr = get_kriteria_weights()
    subkriteria_weights, subkriteria_cr = get_subkriteria_weights()
    guru_list = get_data("guru")
    nilai_subkriteria = get_data("nilai_subkriteria")
    
    results = []
    for guru in guru_list:
        total_score = 0
        detail_scores = {}
        
        for id_kriteria, kriteria_weight in kriteria_weights.items():
            subs = subkriteria_weights.get(id_kriteria, {})
            kriteria_score = 0
            
            for id_sub, sub_weight in subs.items():
                nilai = next((ns['nilai'] for ns in nilai_subkriteria 
                           if ns['id_guru'] == guru['id_guru'] and ns['id_subkriteria'] == id_sub), 0)
                kriteria_score += nilai * sub_weight
            
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

# Fungsi-fungsi tampilan
def show_dashboard():
    st.header("Dashboard")
    st.write("Selamat datang di Sistem AHP untuk Penilaian Kenaikan Status Guru")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Jumlah Guru", len(get_data("guru")))
    with col2:
        st.metric("Jumlah Kriteria", len(get_data("kriteria")))
    with col3:
        st.metric("Jumlah Subkriteria", len(get_data("subkriteria")))

def show_guru_management():
    st.header("Manajemen Data Guru")
    
    tab1, tab2, tab3 = st.tabs(["Daftar Guru", "Tambah Manual", "Import Excel"])
    
    with tab3:
        st.subheader("Import Data Guru")
        
        # 1. Download Template Section
        st.markdown("### Download Template")
        if st.button("Generate Template"):
            try:
                subkriteria_list = get_data("subkriteria")
                template_path = download_guru_template(subkriteria_list)
                
                with open(template_path, "rb") as f:
                    st.download_button(
                        label="Download Template Excel",
                        data=f,
                        file_name="template_import_guru.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            except Exception as e:
                st.error(str(e))
        
        # 2. Upload Section
        st.markdown("### Upload File Excel")
        uploaded_file = st.file_uploader(
            "Pilih file Excel (.xlsx)",
            type=["xlsx"],
            key="guru_upload"
        )
        
        if uploaded_file:
            try:
                # Proses import data
                data_list = import_guru_data(uploaded_file)
                
                # Tampilkan preview
                st.success("File berhasil dibaca")
                st.dataframe(pd.DataFrame(data_list).head())
                
                # Konfirmasi simpan
                if st.button("Simpan ke Database"):
                    if bulk_insert("guru", data_list):
                        st.success(f"Berhasil menyimpan {len(data_list)} data guru")
                        st.session_state.refresh = True
                    else:
                        st.error("Gagal menyimpan ke database")
                        
            except Exception as e:
                st.error(str(e))

def show_kriteria_management():
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
            
            subkriteria_list = get_data("subkriteria", where=f"id_kriteria={selected_kriteria['id_kriteria']}")
            if subkriteria_list:
                df = pd.DataFrame(subkriteria_list)
                st.dataframe(df)
            else:
                st.warning(f"Belum ada subkriteria untuk {selected_kriteria['nama_kriteria']}")
            
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

def show_perbandingan():
    st.header("Perbandingan Kriteria & Subkriteria")
    
    tab1, tab2 = st.tabs(["Perbandingan Kriteria", "Perbandingan Subkriteria"])
    
    with tab1:
        st.subheader("Perbandingan Kriteria (Pairwise Comparison)")
        kriteria_list = get_data("kriteria")
        
        if len(kriteria_list) < 2:
            st.warning("Minimal harus ada 2 kriteria untuk melakukan perbandingan")
        else:
            existing_comparisons = get_data("perbandingan_kriteria")
            
            if existing_comparisons:
                st.info("Data perbandingan kriteria sudah ada. Anda dapat memperbarui jika diperlukan.")
            
            with st.form("form_perbandingan_kriteria"):
                comparisons = {}
                
                for i in range(len(kriteria_list)):
                    for j in range(i+1, len(kriteria_list)):
                        krit1 = kriteria_list[i]
                        krit2 = kriteria_list[j]
                        
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
                        
                        key = f"{krit1['id_kriteria']}_{krit2['id_kriteria']}"
                        label = f"{krit1['nama_kriteria']} vs {krit2['nama_kriteria']}"
                        
                        scale = np.concatenate([
                            np.arange(1/9, 1, 0.5),
                            np.arange(1, 10, 0.5)
                        ])
                        
                        comparisons[key] = st.select_slider(
                            label,
                            options=scale,
                            value=existing_value if existing_value else 1.0,
                            format_func=lambda x: f"{x:.2f}" if x < 1 else f"{x:.0f}"
                        )
                
                submitted = st.form_submit_button("Simpan Perbandingan")
                if submitted:
                    conn = create_connection()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM perbandingan_kriteria")
                    conn.commit()
                    
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
            format_func=lambda x: x['nama_kriteria'],
            key="select_kriteria_perbandingan"
        )
        
        subkriteria_list = get_data("subkriteria", where=f"id_kriteria={selected_kriteria['id_kriteria']}")
        
        if len(subkriteria_list) < 2:
            st.warning(f"Minimal harus ada 2 subkriteria untuk {selected_kriteria['nama_kriteria']} untuk melakukan perbandingan")
        else:
            existing_comparisons = get_data(
                "perbandingan_subkriteria", 
                where=f"id_kriteria={selected_kriteria['id_kriteria']}"
            )
            
            if existing_comparisons:
                st.info(f"Data perbandingan subkriteria untuk {selected_kriteria['nama_kriteria']} sudah ada. Anda dapat memperbarui jika diperlukan.")
            
            with st.form("form_perbandingan_subkriteria"):
                comparisons = {}
                
                for i in range(len(subkriteria_list)):
                    for j in range(i+1, len(subkriteria_list)):
                        sub1 = subkriteria_list[i]
                        sub2 = subkriteria_list[j]
                        
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
                        
                        key = f"{sub1['id_subkriteria']}_{sub2['id_subkriteria']}"
                        label = f"{sub1['nama_subkriteria']} vs {sub2['nama_subkriteria']}"
                        
                        scale = np.concatenate([
                            np.arange(1/9, 1, 0.5),
                            np.arange(1, 10, 0.5)
                        ])
                        
                        comparisons[key] = st.select_slider(
                            label,
                            options=scale,
                            value=existing_value if existing_value else 1.0,
                            format_func=lambda x: f"{x:.2f}" if x < 1 else f"{x:.0f}"
                        )
                
                submitted = st.form_submit_button("Simpan Perbandingan Subkriteria")
                if submitted:
                    conn = create_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "DELETE FROM perbandingan_subkriteria WHERE id_kriteria=%s",
                        (selected_kriteria['id_kriteria'],)
                    )
                    conn.commit()
                    
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

def show_penilaian():
    st.header("Penilaian Guru")
    
    tab1, tab2, tab3 = st.tabs([
        "Input Manual", 
        "Import Nilai", 
        "History Penilaian"
    ])
    
    with tab1:
        # Kode input manual yang sudah ada
        guru_list = get_data("guru")
        if not guru_list:
            st.warning("Belum ada data guru. Silakan tambah guru terlebih dahulu.")
            return
        
        selected_guru = st.selectbox(
            "Pilih Guru",
            guru_list,
            format_func=lambda x: f"{x['nama_guru']} ({x['nip']})",
            key="select_guru_penilaian"
        )
        
        kriteria_list = get_data("kriteria")
        if not kriteria_list:
            st.warning("Belum ada kriteria yang ditentukan")
            return
        
        with st.form(key="form_penilaian_guru"):
            nilai_subkriteria = {}
            
            for kriteria in kriteria_list:
                st.subheader(f"Kriteria: {kriteria['nama_kriteria']}")
                
                subkriteria_list = get_data(
                    "subkriteria", 
                    where=f"id_kriteria={kriteria['id_kriteria']}"
                )
                
                if not subkriteria_list:
                    st.warning(f"Belum ada subkriteria untuk {kriteria['nama_kriteria']}")
                    continue
                
                for sub in subkriteria_list:
                    existing_nilai = get_data(
                        "nilai_subkriteria",
                        where=f"id_guru={selected_guru['id_guru']} AND id_subkriteria={sub['id_subkriteria']}"
                    )
                    
                    default_value = 3
                    if existing_nilai:
                        default_value = int(existing_nilai[0]['nilai'])
                    
                    nilai = st.number_input(
                        f"Nilai untuk {sub['nama_subkriteria']} (1-5)",
                        min_value=1,
                        max_value=5,
                        value=default_value,
                        step=1,
                        key=f"nilai_{sub['id_subkriteria']}"
                    )
                    nilai_subkriteria[sub['id_subkriteria']] = int(nilai)
            
            submitted = st.form_submit_button("Simpan Penilaian")
            if submitted:
                for sub_id, nilai in nilai_subkriteria.items():
                    existing = get_data(
                        "nilai_subkriteria",
                        where=f"id_guru={selected_guru['id_guru']} AND id_subkriteria={sub_id}"
                    )
                    
                    if existing:
                        update_data(
                            "nilai_subkriteria",
                            {'nilai': nilai, 'tanggal_penilaian': datetime.now().date()},
                            f"id_nilai={existing[0]['id_nilai']}"
                        )
                    else:
                        data = {
                            'id_guru': selected_guru['id_guru'],
                            'id_subkriteria': sub_id,
                            'nilai': nilai,
                            'tanggal_penilaian': datetime.now().date()
                        }
                        save_data("nilai_subkriteria", data)
                
                st.success("Penilaian berhasil disimpan")
                st.experimental_rerun()
    with tab2:
        st.subheader("Import Nilai dari Excel")
        
        # Dapatkan data referensi
        guru_list = get_data("guru")
        subkriteria_list = get_data("subkriteria")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Download Template
            if st.button("Download Template Excel"):
                if not guru_list or not subkriteria_list:
                    st.warning("Data guru atau subkriteria belum lengkap")
                else:
                    try:
                        template_path = download_nilai_template(guru_list, subkriteria_list)
                        with open(template_path, "rb") as f:
                            st.download_button(
                                label="Klik untuk Download",
                                data=f,
                                file_name="template_nilai_guru.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
        
        with col2:
            # Upload File
            uploaded_file = st.file_uploader(
                "Pilih file Excel",
                type=["xlsx"],
                key="nilai_upload"
            )
            
            if uploaded_file:
                try:
                    # Proses import file
                    df = pd.read_excel(uploaded_file, sheet_name="Data_Nilai", engine='openpyxl')
                    
                    # Validasi
                    if 'NIP' not in df.columns:
                        raise ValueError("Kolom 'NIP' tidak ditemukan")
                    
                    st.success("File berhasil dibaca")
                    st.dataframe(df.head(3))
                    
                    if st.button("Proses Import"):
                        with st.spinner("Memproses data..."):
                            # Konversi ke format database
                            data_nilai = []
                            subkriteria_map = {sub['nama_subkriteria']: sub['id_subkriteria'] for sub in subkriteria_list}
                            
                            for _, row in df.iterrows():
                                nip = str(row['NIP'])
                                guru = next((g for g in guru_list if g['nip'] == nip), None)
                                
                                if not guru:
                                    continue
                                
                                for sub in subkriteria_list:
                                    if sub['nama_subkriteria'] in df.columns:
                                        nilai = row[sub['nama_subkriteria']]
                                        if pd.notna(nilai) and 1 <= nilai <= 5:
                                            data_nilai.append({
                                                'id_guru': guru['id_guru'],
                                                'id_subkriteria': sub['id_subkriteria'],
                                                'nilai': int(nilai),
                                                'tanggal_penilaian': pd.to_datetime(row['Tanggal Penilaian']).date() if 'Tanggal Penilaian' in df.columns else datetime.now().date()
                                            })
                            
                            # Simpan ke database
                            if bulk_insert("nilai_subkriteria", data_nilai):
                                st.success(f"Berhasil mengimport {len(data_nilai)} data nilai")
                                st.session_state.refresh = True
                            else:
                                st.error("Gagal menyimpan ke database")
                
                except Exception as e:
                    st.error(f"Error memproses file: {str(e)}")
    
    with tab3:
        st.subheader("History Penilaian")
        
        # Pilih guru untuk melihat history
        guru_list = get_data("guru")
        selected_guru = st.selectbox(
            "Pilih Guru",
            guru_list,
            format_func=lambda x: f"{x['nama_guru']} ({x['nip']})",
            key="select_guru_history"
        )
        
        if selected_guru:
            # Dapatkan history penilaian
            query = f"""
            SELECT s.nama_subkriteria, n.nilai, n.tanggal_penilaian 
            FROM nilai_subkriteria n
            JOIN subkriteria s ON n.id_subkriteria = s.id_subkriteria
            WHERE n.id_guru = {selected_guru['id_guru']}
            ORDER BY n.tanggal_penilaian DESC
            """
            history = get_data(query=query)
            
            if history:
                # Tampilkan dalam bentuk tabel
                df = pd.DataFrame(history)
                st.dataframe(df)
                
                # Tampilkan grafik trend nilai
                st.subheader("Perkembangan Nilai")
                pivot_df = df.pivot_table(
                    index='tanggal_penilaian',
                    columns='nama_subkriteria',
                    values='nilai',
                    aggfunc='mean'
                )
                st.line_chart(pivot_df)
            else:
                st.info("Belum ada data penilaian untuk guru ini")
def show_hasil_perangkingan():
    st.header("Hasil Perangkingan Guru")
    
    if st.button("Hitung Ulang Perangkingan"):
        with st.spinner("Menghitung perangkingan..."):
            results, kriteria_cr, subkriteria_cr = calculate_total_scores()
            
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
    
    st.subheader("Daftar Perangkingan Guru")
    
    results_db = get_data("hasil_ahp", "id_guru, total_nilai, tanggal_hitung")
    guru_list = get_data("guru")
    
    if not results_db:
        st.warning("Belum ada hasil perangkingan. Silakan klik tombol 'Hitung Ulang Perangkingan'")
    else:
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
        
        st.subheader("Informasi Konsistensi")
        
        kriteria_weights, kriteria_cr = get_kriteria_weights()
        st.write(f"**Kriteria** - Consistency Ratio (CR): {kriteria_cr:.4f}")
        st.write(check_consistency(kriteria_cr))
        
        subkriteria_weights, subkriteria_cr = get_subkriteria_weights()
        st.write("**Subkriteria**")
        for id_kriteria, cr in subkriteria_cr.items():
            kriteria = next((k for k in get_data("kriteria") if k['id_kriteria'] == id_kriteria), None)
            if kriteria:
                st.write(f"- {kriteria['nama_kriteria']}: CR = {cr:.4f} ({check_consistency(cr)})")
def download_template():
    """Membuat template file Excel untuk import data"""
    # Buat template untuk import guru
    guru_template = pd.DataFrame(columns=[
        'nama_guru', 
        'nip', 
        'jabatan', 
        'tanggal_masuk'
    ])
    
    # Isi dengan contoh data
    guru_template.loc[0] = {
        'nama_guru': 'Nama Guru Contoh',
        'nip': '1234567890',
        'jabatan': 'Guru Mata Pelajaran',
        'tanggal_masuk': '2023-01-01'
    }
    
    # Buat template untuk import nilai
    subkriteria_list = get_data("subkriteria")
    nilai_columns = ['nip', 'tanggal_penilaian'] + [sub['nama_subkriteria'] for sub in subkriteria_list]
    nilai_template = pd.DataFrame(columns=nilai_columns)
    
    # Isi dengan contoh data
    if len(nilai_columns) > 2:  # Pastikan ada subkriteria
        contoh_nilai = {
            'nip': '1234567890',
            'tanggal_penilaian': datetime.now().date().strftime("%Y-%m-%d")
        }
        # Isi nilai untuk 3 subkriteria pertama sebagai contoh
        for sub in subkriteria_list[:3]:
            contoh_nilai[sub['nama_subkriteria']] = 3
            
        nilai_template.loc[0] = contoh_nilai
    
    # Simpan ke Excel dengan 2 sheet
    template_path = 'template_import_guru.xlsx'
    with pd.ExcelWriter(template_path) as writer:
        guru_template.to_excel(writer, sheet_name='Data_Guru', index=False)
        nilai_template.to_excel(writer, sheet_name='Data_Nilai', index=False)
    
    return template_path
# Main Application
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
        show_dashboard()
    elif menu == "Manajemen Guru":
        show_guru_management()
    elif menu == "Manajemen Kriteria & Subkriteria":
        show_kriteria_management()
    elif menu == "Perbandingan Kriteria & Subkriteria":
        show_perbandingan()
    elif menu == "Penilaian Guru":
        show_penilaian()
    elif menu == "Hasil Perangkingan":
        show_hasil_perangkingan()

if __name__ == "__main__":
    main()