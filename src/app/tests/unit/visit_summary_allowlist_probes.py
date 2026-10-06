"""Adversarial / red-team probes for the visit-summary allowlist (v2): (label, expected_eligible).

Copied verbatim from the research artefact round5-probes.py (summary-doc-allowlist, r4-f-05/r4-f-09).
"""
# (label, expected_eligible) adversarial + red-team probes
P = [
 ("AVS",1),("Visit Summaries",1),("Summary of Visit",1),("Ambulatory Summary",1),("Office Visit",1),("Clinic Visit",1),
 ("Follow Up Visit",1),("Outpatient Note",1),("ER Note",1),("Emergency Room Note",1),("Emergency Medicine Note",1),("ED-Note",1),
 ("H and P",1),("H/P",1),("History/Physical",1),("Telephone Note",1),("Phone Note",1),("Readmission Note",1),("C-CDA",1),("CCDA",1),
 ("Critical Care Note",1),("Hospital Course",1),("Progress\u00a0Note",1),("Progress  Note\t",1),("After Visit Summary",1),
 ("Depart Summary",1),("Discharge Summary",1),("Encounter Summary",1),("CCD Document",1),("Progress Notes",1),("Progress Note Generic",1),
 ("Consultation Note Generic",1),("Consults",1),("Rheumatology Consultation",1),("Telemedicine Consultation",1),("Admission Note Physician",1),
 ("History and Physical",1),("H&P",1),("Interval H&P Note",1),("ED Note Physician",1),("ED Provider Notes",1),("Telephone Encounter",1),
 ("Enhanced Note",1),("Op Note",1),("Operative Report",1),("Operative Note",1),("Procedure Note",1),("Brief Op Note",1),("OR Surgeon Note",1),
 ("Endoscopy Report",1),("Physical Therapy Note",1),("Occupational Therapy Note",1),("Social Work Note",1),("PT Progress Note",1),
 ("Skilled Nursing Facility Progress Note",1),("Primary Care Office Visit Note",1),("Practice Visit Summary",1),("Inpatient Clinical Summary",1),
 ("Wound Care Progress Note",1),("Urgent Care Note",1),("Follow-up Note",1),("Behavioral Health Progress Note",1),
 # expected excluded
 ("Consult Request",0),("Consult Order",0),("Consultant Report",0),("Discharge Summary Nursing",0),("Telephone Encounter Nursing",0),
 ("Progress Note-Text",0),("Progress Note \u2013 Text",0),("Height Weight Allergy Rule - Text",0),("Summary of Care Referral",0),
 ("Transition of Care Referral Outbound",0),("Nursing Note",0),("ED Note Nursing",0),("Progress Note Nursing",0),("Nursing Narrative Note",0),
 ("Discharge Note Nursing",0),("Pathology Consultation",0),("Surgical Pathology Report",0),("Anesthesia Preoperative Evaluation",0),
 ("Anesthesia Procedure Notes",0),("Anesthesia Progress Note",0),("Patient Instructions",0),("Discharge Instructions",0),
 ("Ambulatory Visit Instructions",0),("Diagnostic Imaging Study",0),("Radiology Reports",0),("Radiology Procedure Report",0),
 ("Laboratory Report",0),("Lab Report Narrative",0),("Plan of Care",0),("Result Encounter Note",0),("Education Note",0),
 ("Periop Patient Education",0),("Referral Letter",0),("accd",0),("med note",0),("shed",0),("Admission Criteria Note",0),
 ("Main OR Intraoperative Record",0),("Pregnancy Summary Document",0),("Other",0),("",0),(None,0),("Waveform Strip",0),
 ("Echo Report",0),("CT Pelvis W/O Contrast",0),("XR Knee 3 Views Left",0),("Cancer Staging Documentation",0),("Transfer Note",0),
 ("Procedures",0),("Amb Med Review Add",0),("Sleep Study",0),
]
