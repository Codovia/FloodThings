"""Additive report-position provenance; existing report/migration schema stays frozen."""
from sqlalchemy import MetaData,Table,Column,String,DateTime,ForeignKey,CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
metadata=MetaData()
Table('citizen_reports',metadata,Column('id',UUID(as_uuid=False),primary_key=True))
positions=Table('citizen_report_positions',metadata,
    Column('report_id',UUID(as_uuid=False),ForeignKey('citizen_reports.id'),primary_key=True),
    Column('position_source',String(30),nullable=False),
    Column('accuracy_kind',String(30),nullable=False),
    Column('location_selected_at',DateTime(timezone=True)),
    CheckConstraint("(position_source='BROWSER_GPS' AND accuracy_kind='BROWSER_REPORTED') OR (position_source='USER_SELECTED_MAP' AND accuracy_kind='USER_ESTIMATED')"))
POSITION_TABLES=[positions]
