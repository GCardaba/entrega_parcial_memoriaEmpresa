# database/setup.py
class PostgreSQLSetup:
  """Set up a local PostgreSQL instance with required extensions"""
  
  def __init__(self, db_name, user, password):
      self.db_name = db_name
      self.user = user
      self.password = password
  
  def create_database(self):
      """Create database if it doesn't exist"""
      # Connect to default 'postgres' database first
      conn = psycopg2.connect(
          dbname="postgres",
          user=self.user,
          password=self.password
      )
      conn.autocommit = True
      cursor = conn.cursor()
      
      # Check if database exists
      cursor.execute(f"SELECT 1 FROM pg_database WHERE datname='{self.db_name}'")
      if not cursor.fetchone():
          cursor.execute(f"CREATE DATABASE {self.db_name}")
      
      cursor.close()
      conn.close()
  
  def setup_extensions(self):
      """Set up required extensions and configurations"""
      conn = psycopg2.connect(
          dbname=self.db_name,
          user=self.user,
          password=self.password
      )
      conn.autocommit = True
      cursor = conn.cursor()
      
      # Enable extensions
      cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
      
      # Configure PostgreSQL parameters
      cursor.execute("ALTER SYSTEM SET track_io_timing = on")
      cursor.execute("ALTER SYSTEM SET pg_stat_statements.track = 'all'")
      
      # Reload configuration
      cursor.execute("SELECT pg_reload_conf()")
      
      cursor.close()
      conn.close()