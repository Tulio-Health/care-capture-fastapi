from sqlalchemy import Column, String, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class RefCmsProviderData(Base):
    __tablename__ = 'ref_cms_provider_data_loc'

    id = Column(UUID(as_uuid=True), primary_key=True)
    npi = Column(String)
    ind_pac_id = Column(String)
    ind_enrl_id = Column(String)
    provider_last_name = Column(String)
    provider_first_name = Column(String)
    provider_middle_name = Column(String)
    med_sch = Column(String)
    grd_yr = Column(String)
    pri_spec = Column(String)
    sec_spec_1 = Column(String)
    sec_spec_2 = Column(String)
    sec_spec_3 = Column(String)
    sec_spec_4 = Column(String)
    sec_spec_all = Column(String)
    facility_name = Column(String)
    org_pac_id = Column(String)
    num_org_mem = Column(String)
    adr_ln_1 = Column(String)
    adr_ln_2 = Column(String)
    city_town = Column(String)
    zip_code = Column(String)
    telephone_number = Column(String)
    adrs_id = Column(String)
    suffix = Column(String)
    credentials = Column(String)
    state_code = Column(String)
    gndr = Column(String)
    telehlth = Column(String)
    ln_2_sprs = Column(String)
    ind_assgn = Column(String)
    grp_assgn = Column(String)
    timezone = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)