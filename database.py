import mysql.connector

def create_connection():
    """Membuat koneksi ke database MySQL"""
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="sistem_ahp_guru"
        )
        return conn
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

def init_database():
    """Inisialisasi struktur database"""
    conn = create_connection()
    if conn is None:
        return False
    
    cursor = conn.cursor()
    
    # Buat tabel jika belum ada
    tables = [
        """
        CREATE TABLE IF NOT EXISTS guru (
            id_guru INT AUTO_INCREMENT PRIMARY KEY,
            nama_guru VARCHAR(100) NOT NULL,
            nip VARCHAR(20) NOT NULL UNIQUE,
            jabatan VARCHAR(50),
            tanggal_masuk DATE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kriteria (
            id_kriteria INT AUTO_INCREMENT PRIMARY KEY,
            nama_kriteria VARCHAR(100) NOT NULL,
            deskripsi TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS subkriteria (
            id_subkriteria INT AUTO_INCREMENT PRIMARY KEY,
            id_kriteria INT NOT NULL,
            nama_subkriteria VARCHAR(100) NOT NULL,
            deskripsi TEXT,
            FOREIGN KEY (id_kriteria) REFERENCES kriteria(id_kriteria)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS nilai_subkriteria (
            id_nilai INT AUTO_INCREMENT PRIMARY KEY,
            id_guru INT NOT NULL,
            id_subkriteria INT NOT NULL,
            nilai FLOAT NOT NULL,
            tanggal_penilaian DATE,
            FOREIGN KEY (id_guru) REFERENCES guru(id_guru),
            FOREIGN KEY (id_subkriteria) REFERENCES subkriteria(id_subkriteria)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS perbandingan_kriteria (
            id_perbandingan INT AUTO_INCREMENT PRIMARY KEY,
            id_kriteria1 INT NOT NULL,
            id_kriteria2 INT NOT NULL,
            nilai_perbandingan FLOAT NOT NULL,
            FOREIGN KEY (id_kriteria1) REFERENCES kriteria(id_kriteria),
            FOREIGN KEY (id_kriteria2) REFERENCES kriteria(id_kriteria)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS perbandingan_subkriteria (
            id_perbandingan INT AUTO_INCREMENT PRIMARY KEY,
            id_kriteria INT NOT NULL,
            id_subkriteria1 INT NOT NULL,
            id_subkriteria2 INT NOT NULL,
            nilai_perbandingan FLOAT NOT NULL,
            FOREIGN KEY (id_kriteria) REFERENCES kriteria(id_kriteria),
            FOREIGN KEY (id_subkriteria1) REFERENCES subkriteria(id_subkriteria),
            FOREIGN KEY (id_subkriteria2) REFERENCES subkriteria(id_subkriteria)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hasil_ahp (
            id_hasil INT AUTO_INCREMENT PRIMARY KEY,
            id_guru INT NOT NULL,
            total_nilai FLOAT NOT NULL,
            tanggal_hitung DATETIME,
            FOREIGN KEY (id_guru) REFERENCES guru(id_guru)
        )
        """
    ]
    
    try:
        for table in tables:
            cursor.execute(table)
        conn.commit()
        return True
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return False
    finally:
        cursor.close()
        conn.close()