import streamlit as st
import numpy as np
import pandas as pd
import re
from streamlit_option_menu import option_menu
from datetime import datetime
from database import create_connection, init_database, bulk_insert, get_data
from ahp_calculations import *
from utils.template_utils import download_guru_template, download_nilai_template
from utils.import_utils import import_guru_data, import_nilai_data
from utils.stats_utils import calculate_spearman_rank
from utils.db_functions import *

# Inisialisasi database
init_database()

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
def check_consistency(cr):
    """Memberikan penjelasan tentang consistency ratio"""
    if cr < 0.1:
        return "Konsisten (CR < 0.1)"
    elif cr < 0.2:
        return "Cukup Konsisten (0.1 ≤ CR < 0.2)"
    else:
        return "Tidak Konsisten (CR ≥ 0.2), perlu revisi perbandingan!"
def display_ahp_results(matrix, criteria_names):
    """Menampilkan hasil perhitungan AHP"""
    result = calculate_ahp(matrix)
    
    st.subheader("Matriks Perbandingan")
    st.dataframe(pd.DataFrame(matrix, index=criteria_names, columns=criteria_names))
    
    st.subheader("Matriks Normalisasi")
    st.dataframe(pd.DataFrame(result['normalized_matrix'], 
                   index=criteria_names, columns=criteria_names))
    
    st.subheader("Bobot Prioritas")
    df_weights = pd.DataFrame({
        'Kriteria': criteria_names,
        'Bobot': result['weights'],
        'Persentase': (result['weights'] * 100).round(2)
    })
    st.dataframe(df_weights.sort_values('Bobot', ascending=False))
    
    st.subheader("Analisis Konsistensi")
    col1, col2, col3 = st.columns(3)
    col1.metric("λ max", f"{result['lambda_max']:.4f}")
    col2.metric("CI", f"{result['ci']:.4f}")
    col3.metric("CR", f"{result['cr']:.4f}")
    
    if result['cr'] < 0.1:
        st.success("Konsisten (CR < 0.1)")
    else:
        st.error("Tidak Konsisten (CR ≥ 0.1)")

def show_perbandingan_kriteria_crud():
    st.header("📊 Kelola Perbandingan Kriteria")
    
    kriteria_list = get_data("kriteria")
    if len(kriteria_list) < 2:
        st.warning("❌ Minimal harus ada 2 kriteria untuk perbandingan!")
        return
    
    # Dapatkan data perbandingan yang sudah ada
    existing_comps = get_perbandingan_kriteria()
    
    # Tampilkan matriks perbandingan
    st.subheader("Matriks Perbandingan Saat Ini")
    if existing_comps:
        display_comparison_matrix(kriteria_list, existing_comps, "kriteria")
    else:
        st.info("Belum ada data perbandingan.")
    
    # Form untuk input perbandingan
    st.subheader("Input Perbandingan")
    with st.form("form_perbandingan_kriteria"):
        comparison_data = {}
        
        # Buat slider untuk setiap pasangan kriteria
        for i in range(len(kriteria_list)):
            for j in range(i+1, len(kriteria_list)):
                krit1 = kriteria_list[i]
                krit2 = kriteria_list[j]
                
                # Cari nilai yang sudah ada
                existing_value = 1.0  # Default
                for comp in existing_comps:
                    if (comp["id_kriteria1"] == krit1["id_kriteria"] and comp["id_kriteria2"] == krit2["id_kriteria"]) or \
                       (comp["id_kriteria1"] == krit2["id_kriteria"] and comp["id_kriteria2"] == krit1["id_kriteria"]):
                        existing_value = comp["nilai_perbandingan"]
                        break
                
                # Input slider
                nilai = st.slider(
                    f"{krit1['nama_kriteria']} vs {krit2['nama_kriteria']}",
                    min_value=1/9.0,
                    max_value=9.0,
                    value=existing_value,
                    step=0.1,
                    format="%.1f",
                    key=f"kriteria_{krit1['id_kriteria']}_{krit2['id_kriteria']}"
                )
                comparison_data[(krit1["id_kriteria"], krit2["id_kriteria"])] = nilai
        
        col1, col2, col3 = st.columns(3)
        with col1:
            submitted = st.form_submit_button("💾 Simpan Perbandingan")
        with col2:
            reset = st.form_submit_button("🔄 Reset Semua")
        with col3:
            delete = st.form_submit_button("🗑️ Hapus Perbandingan")
        
        if submitted:
            success = True
            for (id1, id2), nilai in comparison_data.items():
                if not save_perbandingan_kriteria(id1, id2, nilai):
                    success = False
            if success:
                st.success("✅ Perbandingan berhasil disimpan!")
                st.rerun()
        
        if reset:
            if reset_perbandingan_kriteria():
                st.success("🔄 Perbandingan direset!")
                st.rerun()
        
        if delete:
            if len(existing_comps) > 0:
                for comp in existing_comps:
                    delete_perbandingan_kriteria(comp["id_kriteria1"], comp["id_kriteria2"])
                st.success("🗑️ Semua perbandingan dihapus!")
                st.rerun()

def show_perbandingan_subkriteria_crud():
    st.header("📊 Kelola Perbandingan Subkriteria")
    
    # Pilih kriteria terlebih dahulu
    kriteria_list = get_data("kriteria")
    selected_kriteria = st.selectbox(
        "Pilih Kriteria",
        kriteria_list,
        format_func=lambda x: x["nama_kriteria"],
        key="select_kriteria_for_sub"
    )
    
    subkriteria_list = get_data(
        "subkriteria", 
        where=f"id_kriteria={selected_kriteria['id_kriteria']}"
    )
    
    if len(subkriteria_list) < 2:
        st.warning("❌ Minimal harus ada 2 subkriteria untuk perbandingan!")
        return
    
    # Dapatkan data perbandingan yang sudah ada
    existing_comps = get_perbandingan_subkriteria(selected_kriteria["id_kriteria"])
    
    # Tampilkan matriks perbandingan
    st.subheader(f"Matriks Perbandingan Subkriteria ({selected_kriteria['nama_kriteria']})")
    if existing_comps:
        display_comparison_matrix(subkriteria_list, existing_comps, "subkriteria")
    else:
        st.info("Belum ada data perbandingan.")
    
    # Form untuk input perbandingan
    st.subheader("Input Perbandingan")
    with st.form("form_perbandingan_subkriteria"):
        comparison_data = {}
        
        # Buat slider untuk setiap pasangan subkriteria
        for i in range(len(subkriteria_list)):
            for j in range(i+1, len(subkriteria_list)):
                sub1 = subkriteria_list[i]
                sub2 = subkriteria_list[j]
                
                # Cari nilai yang sudah ada
                existing_value = 1.0  # Default
                for comp in existing_comps:
                    if (comp["id_subkriteria1"] == sub1["id_subkriteria"] and comp["id_subkriteria2"] == sub2["id_subkriteria"]) or \
                       (comp["id_subkriteria1"] == sub2["id_subkriteria"] and comp["id_subkriteria2"] == sub1["id_subkriteria"]):
                        existing_value = comp["nilai_perbandingan"]
                        break
                
                # Input slider
                nilai = st.slider(
                    f"{sub1['nama_subkriteria']} vs {sub2['nama_subkriteria']}",
                    min_value=1/9.0,
                    max_value=9.0,
                    value=existing_value,
                    step=0.1,
                    format="%.1f",
                    key=f"subkriteria_{sub1['id_subkriteria']}_{sub2['id_subkriteria']}"
                )
                comparison_data[(sub1["id_subkriteria"], sub2["id_subkriteria"])] = nilai
        
        col1, col2, col3 = st.columns(3)
        with col1:
            submitted = st.form_submit_button("💾 Simpan Perbandingan")
        with col2:
            reset = st.form_submit_button("🔄 Reset")
        with col3:
            delete = st.form_submit_button("🗑️ Hapus")
        
        if submitted:
            success = True
            for (id1, id2), nilai in comparison_data.items():
                if not save_perbandingan_subkriteria(selected_kriteria["id_kriteria"], id1, id2, nilai):
                    success = False
            if success:
                st.success("✅ Perbandingan berhasil disimpan!")
                st.rerun()
        
        if reset:
            if reset_perbandingan_subkriteria(selected_kriteria["id_kriteria"]):
                st.success("🔄 Perbandingan direset!")
                st.rerun()
        
        if delete:
            if len(existing_comps) > 0:
                for comp in existing_comps:
                    delete_perbandingan_subkriteria(
                        selected_kriteria["id_kriteria"],
                        comp["id_subkriteria1"],
                        comp["id_subkriteria2"]
                    )
                st.success("🗑️ Semua perbandingan dihapus!")
                st.rerun()
def calculate_total_scores():
    kriteria_weights, kriteria_cr, kriteria_ri = get_kriteria_weights()
    subkriteria_weights, subkriteria_cr, subkriteria_ri = get_subkriteria_weights()
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
    
    return sorted(results, key=lambda x: x['total_score'], reverse=True), kriteria_cr, kriteria_ri, subkriteria_cr, subkriteria_ri

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

def show_tahun_ajaran_management():
    st.header("🎓 Manajemen Tahun Ajaran")
    
    tab1, tab2, tab3 = st.tabs(["Daftar Tahun Ajaran", "Pengaturan Tahun Aktif","Tambah Tahun Ajaran"])
    
    with tab1:
        st.subheader("Daftar Tahun Ajaran")
        tahun_ajaran_list = get_all_tahun_ajaran()
        
        if tahun_ajaran_list:
            # Format data untuk ditampilkan
            df = pd.DataFrame(tahun_ajaran_list)
            df['tanggal_mulai'] = pd.to_datetime(df['tanggal_mulai']).dt.strftime('%d/%m/%Y')
            df['tanggal_selesai'] = pd.to_datetime(df['tanggal_selesai']).dt.strftime('%d/%m/%Y')
            
            st.dataframe(
                df[['tahun', 'semester', 'is_aktif', 'tanggal_mulai', 'tanggal_selesai']],
                column_config={
                    "tahun": "Tahun Ajaran",
                    "semester": "Semester",
                    "is_aktif": st.column_config.CheckboxColumn("Aktif?"),
                    "tanggal_mulai": "Mulai",
                    "tanggal_selesai": "Selesai"
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.warning("Belum ada data tahun ajaran")
    
    with tab2:
        st.subheader("Atur Tahun Ajaran Aktif")
        tahun_ajaran_list = get_all_tahun_ajaran()
        
        if not tahun_ajaran_list:
            st.warning("Tidak ada tahun ajaran yang tersedia")
            return
        
        # Dapatkan tahun ajaran yang aktif saat ini
        tahun_aktif = next((t for t in tahun_ajaran_list if t['is_aktif']), None)
        
        selected_tahun = st.selectbox(
            "Pilih Tahun Ajaran yang akan diaktifkan",
            tahun_ajaran_list,
            format_func=lambda x: f"{x['tahun']} - {x['semester']} (Aktif)" if x['is_aktif'] else f"{x['tahun']} - {x['semester']}",
            index=tahun_ajaran_list.index(tahun_aktif) if tahun_aktif else 0
        )
        
        if st.button("💾 Set Tahun Ajaran Aktif", type="primary"):
            if set_aktif_tahun_ajaran(selected_tahun['id_tahun_ajaran']):
                st.success(f"Tahun ajaran {selected_tahun['tahun']} semester {selected_tahun['semester']} berhasil diaktifkan!")
                st.rerun()
            else:
                st.error("Gagal mengatur tahun ajaran aktif")
        
        # Tampilkan informasi tahun aktif saat ini
        tahun_aktif = get_aktif_tahun_ajaran()
        if tahun_aktif:
            st.markdown("---")
            st.subheader("Tahun Ajaran Aktif Saat Ini")
            col1, col2, col3 = st.columns(3)
            col1.metric("Tahun Ajaran", tahun_aktif['tahun'])
            col2.metric("Semester", tahun_aktif['semester'])
            col3.metric("Periode", f"{tahun_aktif['tanggal_mulai']} s/d {tahun_aktif['tanggal_selesai']}")
    with tab3:
        st.subheader("Buat Tahun Ajaran Baru")
        
        with st.form("form_tahun_ajaran"):
            col1, col2 = st.columns(2)
            
            with col1:
                tahun = st.text_input("Tahun Ajaran (Format: 2023/2024)*")
                semester = st.selectbox("Semester*", ["Ganjil", "Genap"])
                
            with col2:
                tanggal_mulai = st.date_input("Tanggal Mulai*")
                tanggal_selesai = st.date_input("Tanggal Selesai*")
            
            periode = st.text_input("Nama Periode*", 
                                  help="Contoh: Tahun Ajaran 2023/2024 Semester Ganjil")
            
            submitted = st.form_submit_button("Buat Tahun Ajaran Baru")
            
            if submitted:
                if not all([tahun, semester, periode, tanggal_mulai, tanggal_selesai]):
                    st.error("Semua field bertanda * wajib diisi!")
                elif tanggal_mulai >= tanggal_selesai:
                    st.error("Tanggal mulai harus sebelum tanggal selesai")
                elif not re.match(r"^\d{4}/\d{4}$", tahun):
                    st.error("Format tahun harus YYYY/YYYY (contoh: 2023/2024)")
                else:
                    if create_tahun_ajaran(
                        tahun=tahun,
                        periode=periode,
                        semester=semester,
                        tanggal_mulai=tanggal_mulai.strftime("%Y-%m-%d"),
                        tanggal_selesai=tanggal_selesai.strftime("%Y-%m-%d")
                    ):
                        st.success("Tahun ajaran baru berhasil dibuat! Data guru telah diduplikasi.")
                        st.balloons()
                    else:
                        st.error("Gagal membuat tahun ajaran baru")

def show_guru_management():
    st.header("Manajemen Data Guru")
    
    tab1, tab2, tab3 = st.tabs(["Daftar Guru", "Tambah Manual", "Import Excel"])

    with tab1:
        st.subheader("Daftar Guru")
        
        # Dapatkan data guru dari database
        guru_list = get_data("guru")
        
        if guru_list:
            # Buat DataFrame untuk tampilan yang lebih baik
            df = pd.DataFrame(guru_list)
            
            # Tampilkan tabel dengan opsi edit/hapus
            st.dataframe(df, use_container_width=True)
            
            # Opsi untuk menghapus guru
            st.markdown("### Hapus Data Guru")
            guru_to_delete = st.selectbox(
                "Pilih Guru yang Akan Dihapus",
                options=[(g['id_guru'], g['nama_guru']) for g in guru_list],
                format_func=lambda x: f"{x[1]} (ID: {x[0]})",
                index=0,
                key="delete_guru_select"
            )
            
            if st.button("Hapus Guru Terpilih", type="primary"):
                if delete_guru(guru_to_delete[0]):
                    st.success(f"Guru {guru_to_delete[1]} berhasil dihapus")
                else:
                    st.error("Gagal menghapus data guru")
        else:
            st.warning("Belum ada data guru yang tersimpan")
    
    with tab2:
        st.subheader("Tambah Data Guru Manual")
        
        with st.form("form_tambah_guru"):
            col1, col2 = st.columns(2)
            
            with col1:
                nama_guru = st.text_input("Nama Lengkap*", max_chars=100)
                nip = st.text_input("NIP*", max_chars=18)
                
            with col2:
                jabatan = st.selectbox(
                    "Jabatan*",
                    options=["Guru Kelas", "Guru Mata Pelajaran", "Kepala Sekolah", "Wakil Kepala Sekolah"]
                )
                tanggal_masuk = st.date_input("Tanggal Masuk*")
            
            # Form validation
            submitted = st.form_submit_button("Simpan Data Guru")
            if submitted:
                if not nama_guru or not nip:
                    st.error("Nama dan NIP wajib diisi!")
                else:
                    guru_data = {
                        'nama_guru': nama_guru,
                        'nip': nip,
                        'jabatan': jabatan,
                        'tanggal_masuk': tanggal_masuk.strftime('%Y-%m-%d')
                    }
                    
                    if save_data("guru", guru_data):
                        st.success("Data guru berhasil disimpan!")
                        st.balloons()
                        st.experimental_rerun()
                    else:
                        st.error("Gagal menyimpan data guru")
    
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

def display_ahp_results(matrix, criteria_names):
    """Menampilkan hasil perhitungan AHP secara lengkap"""
    result = calculate_ahp(matrix)
    
    # Tab untuk organisasi tampilan
    tab1, tab2, tab3, tab4 = st.tabs([
        "Matriks Perbandingan", 
        "Matriks Normalisasi", 
        "Bobot Prioritas", 
        "Analisis Konsistensi"
    ])
    
    with tab1:
        st.caption("Matriks Perbandingan Berpasangan")
        df_matrix = pd.DataFrame(matrix, index=criteria_names, columns=criteria_names)
        st.dataframe(df_matrix.style.format("{:.3f}"), use_container_width=True)
    
    with tab2:
        st.caption("Matriks Normalisasi (Jumlah Kolom = 1)")
        df_normalized = pd.DataFrame(
            result['normalized_matrix'],
            index=criteria_names, 
            columns=criteria_names
        )
        st.dataframe(df_normalized.style.format("{:.3f}"), use_container_width=True)
    
    with tab3:
        st.caption("Bobot Prioritas (Eigenvector)")
        df_weights = pd.DataFrame({
            'Kriteria': criteria_names,
            'Bobot': result['weights'],
            'Persentase': (result['weights'] * 100).round(2)
        })
        st.dataframe(
            df_weights.sort_values('Bobot', ascending=False),
            use_container_width=True,
            hide_index=True
        )
    
    with tab4:
        col1, col2, col3 = st.columns(3)
        col1.metric("λ max", f"{result['lambda_max']:.4f}")
        col2.metric("Consistency Index", f"{result['ci']:.4f}")
        col3.metric("Consistency Ratio", f"{result['cr']:.4f}")
        
        st.progress(min(result['cr'] / 0.1, 1.0))
        st.caption(f"Random Index (RI): {result['ri']:.2f}")
        
        if result['cr'] < 0.1:
            st.success("✅ Konsisten (CR < 0.1)")
        elif result['cr'] < 0.2:
            st.warning("⚠️ Cukup Konsisten (0.1 ≤ CR < 0.2)")
        else:
            st.error("❌ Tidak Konsisten (CR ≥ 0.2) - Perlu revisi perbandingan!")

def show_penilaian():
    st.header("Penilaian Guru")
        # Cek tahun ajaran aktif terlebih dahulu
    tahun_aktif = get_aktif_tahun_ajaran()
    if not tahun_aktif:
        st.error("Silakan aktifkan tahun ajaran terlebih dahulu")
        return
    
    st.header(f"Penilaian Guru - {tahun_aktif['tahun']} {tahun_aktif['semester']}")
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
            # Dapatkan history penilaian dengan parameter normal
            history = get_data(
                table_name="nilai_subkriteria n JOIN subkriteria s ON n.id_subkriteria = s.id_subkriteria",
                columns="s.nama_subkriteria, n.nilai, n.tanggal_penilaian",
                where=f"n.id_guru = {selected_guru['id_guru']}"
            )
            
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
def show_ranking_results():
    """Menampilkan hasil perankingan guru"""
    st.title("Hasil Perangkingan Guru")
    
    if st.button("🔄 Hitung Ulang Perangkingan", type="primary"):
        with st.spinner("Menghitung perankingan..."):
            df_results, kriteria_cr, subkriteria_cr = calculate_ranking()
            
            if df_results is None:
                st.error("Tidak dapat menghitung perankingan. Pastikan:")
                st.write("- Ada kriteria dan subkriteria")
                st.write("- Ada data perbandingan berpasangan")
                st.write("- Ada data nilai guru")
                return
            
            # Simpan ke session state
            st.session_state.ranking_results = df_results
            st.session_state.kriteria_cr = kriteria_cr
            st.session_state.subkriteria_cr = subkriteria_cr
    
    if 'ranking_results' not in st.session_state:
        st.warning("Silakan klik tombol 'Hitung Ulang Perangkingan'")
        return
    
    df_results = st.session_state.ranking_results
    
    # Tampilkan hasil utama
    st.subheader("Daftar Perankingan")
    
    # Pilih kolom yang akan ditampilkan
    default_cols = ['Peringkat', 'nama_guru', 'nip', 'total_score']
    detail_cols = [col for col in df_results.columns if col.startswith('Kriteria')]
    
    # Tab untuk tampilan berbeda
    tab1, tab2 = st.tabs(["Tampilan Utama", "Detail Penilaian"])
    
    with tab1:
        # Tampilkan tabel utama
        st.dataframe(
            df_results[default_cols].rename(columns={
                'nama_guru': 'Nama Guru',
                'nip': 'NIP',
                'total_score': 'Total Nilai'
            }),
            use_container_width=True,
            hide_index=True
        )
        
        # Grafik peringkat
        st.subheader("Visualisasi Perankingan")
        chart_data = df_results.head(10).set_index('nama_guru')['total_score']
        st.bar_chart(chart_data)
    
    with tab2:
        # Tampilkan detail penilaian per kriteria
        st.dataframe(
            df_results[default_cols + detail_cols],
            use_container_width=True
        )
        
        # Download hasil
        st.download_button(
            label="📥 Download Hasil (Excel)",
            data=df_results.to_csv(index=False).encode('utf-8'),
            file_name="hasil_perangkingan_guru.csv",
            mime="text/csv"
        )
    
    # Tampilkan informasi konsistensi
    st.subheader("Analisis Konsistensi")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("CR Kriteria", f"{st.session_state.kriteria_cr:.4f}")
        st.write(check_consistency(st.session_state.kriteria_cr))
    
    with col2:
        avg_sub_cr = np.mean(list(st.session_state.subkriteria_cr.values())) if st.session_state.subkriteria_cr else 0
        st.metric("Rata-rata CR Subkriteria", f"{avg_sub_cr:.4f}")
        st.write(check_consistency(avg_sub_cr))
    
    # Tampilkan detail CR subkriteria
    with st.expander("Detail Konsistensi Subkriteria"):
        for id_kriteria, cr in st.session_state.subkriteria_cr.items():
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
    st.set_page_config(
        page_title="Sistem AHP untuk Penilaian Kenaikan Status Guru",
        page_icon="🧑‍🏫",
        layout="wide"
    )
    
    with st.sidebar:
        tahun_aktif = get_aktif_tahun_ajaran()
        if tahun_aktif:
            st.success(f"Tahun Ajaran Aktif: {tahun_aktif['periode']}")
            st.caption(f"Semester: {tahun_aktif['semester']}")
        else:
            st.warning("Belum ada tahun ajaran aktif")
        selected = option_menu(
            menu_title="Menu Utama",
            options=[
                "Dashboard", 
                "Tahun Ajaran",
                "Manajemen Guru", 
                "Manajemen Kriteria",
                "Perbandingan Kriteria", 
                "Perbandingan Subkriteria",
                "Penilaian Guru",
                "Hasil Perangkingan"
            ],
            icons=[
                "speedometer2", 
                "people-fill",
                "people-fill",
                "list-check",
                "bar-chart-line",
                "bar-chart-steps",
                "clipboard-check",
                "trophy-fill"
            ],
            menu_icon="cast",
            default_index=0,
            styles={
                "container": {"padding": "5!important", "background-color": "#f8f9fa"},
                "icon": {"color": "orange", "font-size": "18px"}, 
                "nav-link": {"font-size": "16px", "text-align": "left", "margin":"0px", "--hover-color": "#eee"},
                "nav-link-selected": {"background-color": "#0d6efd"},
            }
        )
    
    st.title("🧑‍🏫 Sistem AHP untuk Penilaian Kenaikan Status Guru")
    
    if selected == "Dashboard":
        show_dashboard()
    elif selected == "Tahun Ajaran":
        show_tahun_ajaran_management()
    elif selected == "Manajemen Guru":
        show_guru_management()
    elif selected == "Manajemen Kriteria":
        show_kriteria_management()
    elif selected == "Perbandingan Kriteria":
        show_perbandingan_kriteria_crud()
    elif selected == "Perbandingan Subkriteria":
        show_perbandingan_subkriteria_crud()
    elif selected == "Penilaian Guru":
        show_penilaian()
    elif selected == "Hasil Perangkingan":
        show_ranking_results()

if __name__ == "__main__":
    main()