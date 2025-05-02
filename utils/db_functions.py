# ========== FUNGSI DATABASE ==========
from database import create_connection, init_database, bulk_insert, get_data
import streamlit as st

# Fungsi-fungsi database

def get_data(table_name, columns="*", where="", order_by=""):
    """Mengambil data dari database"""
    conn = create_connection()
    if conn is None:
        return []
    
    cursor = conn.cursor(dictionary=True)
    query = f"SELECT {columns} FROM {table_name}"
    
    if where:
        query += f" WHERE {where}"
    if order_by:
        query += f" ORDER BY {order_by}"
    
    try:
        cursor.execute(query)
        return cursor.fetchall()
    except Exception as e:
        st.error(f"Error mendapatkan data: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def save_data(table_name, data):
    """Menyimpan data ke database"""
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


# Fungsi CRUD Tahun Ajaran
def create_tahun_ajaran(tahun: str, periode: str, semester: str, tanggal_mulai: str, tanggal_selesai: str):
    """Membuat tahun ajaran baru"""
    conn = create_connection()
    if conn is None:
        return False
    
    try:
        # Nonaktifkan semua tahun ajaran sebelumnya
        cursor = conn.cursor()
        cursor.execute("UPDATE tahun_ajaran SET is_aktif = FALSE")
        
        # Buat tahun ajaran baru
        cursor.execute(
            """INSERT INTO tahun_ajaran 
            (tahun, periode, semester, is_aktif, tanggal_mulai, tanggal_selesai) 
            VALUES (%s, %s, %s, TRUE, %s, %s)""",
            (tahun, periode, semester, tanggal_mulai, tanggal_selesai)
        )
        
        # Dapatkan ID tahun ajaran baru
        new_id = cursor.lastrowid
        
        # Duplikasi data guru dari tahun sebelumnya ke tahun baru
        cursor.execute("""
            INSERT INTO guru (nama_guru, nip, jabatan, tanggal_masuk, id_tahun_ajaran)
            SELECT nama_guru, nip, jabatan, tanggal_masuk, %s 
            FROM guru 
            WHERE id_tahun_ajaran = (
                SELECT id_tahun_ajaran FROM tahun_ajaran 
                WHERE is_aktif = FALSE 
                ORDER BY id_tahun_ajaran DESC LIMIT 1
            )
        """, (new_id,))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Gagal membuat tahun ajaran baru: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def get_aktif_tahun_ajaran():
    """Mendapatkan tahun ajaran yang aktif"""
    conn = create_connection()
    if conn is None:
        return None
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tahun_ajaran WHERE is_aktif = TRUE LIMIT 1")
        return cursor.fetchone()
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None
    finally:
        if conn:
            conn.close()



# Fungsi CRUD Guru
def get_data_guru():
    """Mendapatkan data guru untuk tahun ajaran aktif"""
    tahun_aktif = get_aktif_tahun_ajaran()
    if not tahun_aktif:
        return []
    
    return get_data(
        "guru", 
        where=f"id_tahun_ajaran={tahun_aktif['id_tahun_ajaran']}"
    )
def save_guru(data):
    tahun_aktif = get_aktif_tahun_ajaran()
    if not tahun_aktif:
        st.error("Tidak ada tahun ajaran aktif")
        return False
    
    conn = create_connection()
    if conn is None:
        return False
    
    try:
        cursor = conn.cursor()
        query = """
        INSERT INTO guru 
        (nama_guru, nip, jabatan, tanggal_masuk, id_tahun_ajaran) 
        VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(query, (
            data['nama_guru'], 
            data['nip'], 
            data['jabatan'], 
            data['tanggal_masuk'],
            tahun_aktif['id_tahun_ajaran']
        ))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Database error: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def update_guru_data(updated_rows):
    """Update data guru berdasarkan perubahan di tabel"""
    if not updated_rows:
        return True
    
    conn = create_connection()
    if conn is None:
        return False
    
    try:
        cursor = conn.cursor()
        for row_id, changes in updated_rows.items():
            query = "UPDATE guru SET "
            params = []
            
            for col, val in changes.items():
                query += f"{col} = %s, "
                params.append(val)
            
            query = query.rstrip(", ") + f" WHERE id_guru = %s"
            params.append(row_id)
            
            cursor.execute(query, params)
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error updating data: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def delete_guru(guru_id):
    """
    Menghapus data guru beserta semua data relasinya dari database
    Args:
        guru_id: ID guru yang akan dihapus
    Returns:
        bool: True jika berhasil, False jika gagal
    """
    conn = create_connection()
    if conn is None:
        st.error("Koneksi database gagal")
        return False
    
    try:
        cursor = conn.cursor()
        
        # 1. Hapus data penilaian guru di tabel nilai_subkriteria
        cursor.execute("DELETE FROM nilai_subkriteria WHERE id_guru = %s", (guru_id,))
        st.info(f"Menghapus {cursor.rowcount} data penilaian terkait")
        
        # 2. Hapus data hasil perhitungan AHP jika ada
        cursor.execute("DELETE FROM hasil_ahp WHERE id_guru = %s", (guru_id,))
        st.info(f"Menghapus {cursor.rowcount} data hasil perhitungan")
        
        # 3. Hapus data guru utama
        cursor.execute("DELETE FROM guru WHERE id_guru = %s", (guru_id,))
        deleted_rows = cursor.rowcount
        
        conn.commit()
        
        if deleted_rows > 0:
            st.success(f"Data guru dengan ID {guru_id} berhasil dihapus beserta semua relasinya")
            return True
        else:
            st.warning(f"Tidak ditemukan guru dengan ID {guru_id}")
            return False
            
    except Exception as e:
        conn.rollback()
        st.error(f"Gagal menghapus data: {str(e)}")
        return False
        
    finally:
        if conn:
            conn.close()



# Fungsi CRUD Perbandingan Kriteria
def get_perbandingan_kriteria():
    """Mendapatkan semua data perbandingan kriteria"""
    return get_data("perbandingan_kriteria")

def save_perbandingan_kriteria(id_kriteria1, id_kriteria2, nilai):
    """Menyimpan/update perbandingan kriteria"""
    conn = create_connection()
    if conn is None:
        return False
    
    try:
        cursor = conn.cursor()
        # Cek apakah perbandingan sudah ada
        cursor.execute(
            """SELECT 1 FROM perbandingan_kriteria 
            WHERE (id_kriteria1=%s AND id_kriteria2=%s)
            OR (id_kriteria1=%s AND id_kriteria2=%s)""",
            (id_kriteria1, id_kriteria2, id_kriteria2, id_kriteria1)
        )
        exists = cursor.fetchone()
        
        if exists:
            # Update existing comparison
            cursor.execute(
                """UPDATE perbandingan_kriteria SET nilai_perbandingan=%s
                WHERE (id_kriteria1=%s AND id_kriteria2=%s)""",
                (nilai, id_kriteria1, id_kriteria2)
            )
        else:
            # Insert new comparison
            cursor.execute(
                """INSERT INTO perbandingan_kriteria 
                (id_kriteria1, id_kriteria2, nilai_perbandingan)
                VALUES (%s, %s, %s)""",
                (id_kriteria1, id_kriteria2, nilai)
            )
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Gagal menyimpan perbandingan: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()
def delete_perbandingan_kriteria(id_kriteria1, id_kriteria2):
    """Menghapus perbandingan kriteria"""
    conn = create_connection()
    if conn is None:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            """DELETE FROM perbandingan_kriteria 
            WHERE (id_kriteria1=%s AND id_kriteria2=%s)
            OR (id_kriteria1=%s AND id_kriteria2=%s)""",
            (id_kriteria1, id_kriteria2, id_kriteria2, id_kriteria1)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Gagal menghapus perbandingan: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()
def reset_perbandingan_kriteria():
    """Mereset semua perbandingan kriteria"""
    conn = create_connection()
    if conn is None:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM perbandingan_kriteria")
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Gagal mereset perbandingan: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()



# Fungsi CRUD Perbandingan Subkriteria
def get_perbandingan_subkriteria(id_kriteria):
    """Mendapatkan perbandingan subkriteria untuk kriteria tertentu"""
    return get_data(
        "perbandingan_subkriteria", 
        where=f"id_kriteria={id_kriteria}"
    )

def save_perbandingan_subkriteria(id_kriteria, id_subkriteria1, id_subkriteria2, nilai):
    """Menyimpan/update perbandingan subkriteria"""
    conn = create_connection()
    if conn is None:
        return False
    
    try:
        cursor = conn.cursor()
        # Cek apakah perbandingan sudah ada
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
            # Update existing comparison
            cursor.execute(
                """UPDATE perbandingan_subkriteria SET nilai_perbandingan=%s
                WHERE id_kriteria=%s AND id_subkriteria1=%s AND id_subkriteria2=%s""",
                (nilai, id_kriteria, id_subkriteria1, id_subkriteria2)
            )
        else:
            # Insert new comparison
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

def reset_perbandingan_subkriteria(id_kriteria):
    """Mereset perbandingan subkriteria untuk kriteria tertentu"""
    conn = create_connection()
    if conn is None:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM perbandingan_subkriteria WHERE id_kriteria=%s",
            (id_kriteria,)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Gagal mereset perbandingan: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def set_aktif_tahun_ajaran(tahun_ajaran_id):
    """Mengatur tahun ajaran yang aktif"""
    conn = create_connection()
    if conn is None:
        return False
    
    try:
        cursor = conn.cursor()
        # Nonaktifkan semua tahun ajaran terlebih dahulu
        cursor.execute("UPDATE tahun_ajaran SET is_aktif = FALSE")
        
        # Aktifkan tahun ajaran yang dipilih
        cursor.execute(
            "UPDATE tahun_ajaran SET is_aktif = TRUE WHERE id_tahun_ajaran = %s",
            (tahun_ajaran_id,))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Gagal mengatur tahun ajaran aktif: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def get_all_tahun_ajaran():
    """Mendapatkan semua data tahun ajaran"""
    return get_data("tahun_ajaran", order_by="id_tahun_ajaran DESC")