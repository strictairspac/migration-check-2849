from sqlalchemy import Column,Integer,String,JSON,DateTime,func,ForeignKey,UniqueConstraint
from src.config.database import Base
class DrillPackage(Base):
 __tablename__='drill_packages'
 id=Column(Integer,primary_key=True)
 name=Column(String(120),unique=True,nullable=False)
 recipient_group=Column(String(120),nullable=False)
 alias_token=Column(String(12),nullable=False)
 status=Column(String(20),nullable=False,default='open')
 version=Column(Integer,nullable=False,default=0)
 created_at=Column(DateTime,server_default=func.now())
class DrillAlias(Base):
 __tablename__='drill_aliases'
 __table_args__=(UniqueConstraint('package_id','sample_code'),UniqueConstraint('package_id','seq'))
 id=Column(Integer,primary_key=True)
 package_id=Column(Integer,ForeignKey('drill_packages.id'),nullable=False)
 sample_code=Column(String(160),nullable=False)
 alias=Column(String(40),nullable=False)
 seq=Column(Integer,nullable=False)
class DrillRow(Base):
 __tablename__='drill_rows'
 __table_args__=(UniqueConstraint('package_id','run_id','ordinal'),)
 id=Column(Integer,primary_key=True)
 package_id=Column(Integer,ForeignKey('drill_packages.id'),nullable=False)
 run_id=Column(Integer,ForeignKey('runs.id'),nullable=False)
 ordinal=Column(Integer,nullable=False)
 introduced_version=Column(Integer,nullable=False)
 payload=Column(JSON,nullable=False)
class DrillVersion(Base):
 __tablename__='drill_versions'
 __table_args__=(UniqueConstraint('package_id','version'),)
 id=Column(Integer,primary_key=True)
 package_id=Column(Integer,ForeignKey('drill_packages.id'),nullable=False)
 version=Column(Integer,nullable=False)
 row_count=Column(Integer,nullable=False)
 checksum=Column(String(64),nullable=False)
 added_run_ids=Column(JSON,nullable=False)
 created_at=Column(DateTime,server_default=func.now())
class DrillJob(Base):
 __tablename__='drill_jobs'
 id=Column(Integer,primary_key=True)
 package_id=Column(Integer,ForeignKey('drill_packages.id'),nullable=False)
 run_ids=Column(JSON,nullable=False)
 processed=Column(JSON,nullable=False,default=list)
 target_version=Column(Integer,nullable=False)
 status=Column(String(20),nullable=False,default='queued')
 error=Column(String(1000),nullable=True)
 created_at=Column(DateTime,server_default=func.now())
