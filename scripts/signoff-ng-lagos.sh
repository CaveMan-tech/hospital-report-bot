#!/bin/sh
# Sign-off for the ng-lagos pack. Running a line below records, in the pack file and so in git
# history, that YOU checked that entry against the source named on the line.
#
# Before you run this:
#   1. Put your name in NAME.
#   2. Delete (or comment out) every line you did not personally check. For a contact, "checked"
#      means you test-called the number and it reached the right service, not only that the
#      website lists it. Lines marked TEST-CALL are those.
#   3. If you checked an entry against something other than the source shown, edit --source.
#
#   sh scripts/signoff-ng-lagos.sh      then:  git diff packs/   and commit.
# To undo one:  uv run python -m app.verify unmark ng-lagos <file> <id>
set -eu
NAME=""
[ -n "$NAME" ] || { echo "Put your name in NAME at the top of this script first."; exit 1; }
mark() { uv run python -m app.verify mark ng-lagos "$1" "$2" --by "$NAME" --source "$3"; }


# ---- contacts
mark contacts emergency 'Lagos State Ministry of Health contact page: '"'"'Emergency Line: 767 / 112'"'"'. Then test-call both. https://lagosministryofhealth.org/contact/'   # TEST-CALL
mark contacts legal_aid 'Lagos State Public Defender contact page. Then test-call. https://opdlagosstate.org/contact.html; Backup: Legal Aid Council of Nigeria, Lagos https://legalaidcouncil.gov.ng/contact-us/'   # TEST-CALL
mark contacts dsva 'Lagos DSVA FAQ and contact pages. Then test-call. https://lagosdsva.org/frequently-asked-questionsfaqs/'   # TEST-CALL
mark contacts sarc 'Mirabel Centre contact page. Then test-call. https://mirabelcentre.org/contact-us/'   # TEST-CALL
mark contacts crisis 'SURPIN site footer. Hours unconfirmed: MUST be test-called. https://www.surpinng.com/'   # TEST-CALL

# ---- rights
mark rights emergency 'National Health Act 2014, Official Gazette No. 145 Vol. 101: s.20 on p. A153, s.30 on p. A156 https://scorecard.prb.org/wp-content/uploads/2019/06/Nigeria-National-Health-Act-2014.pdf'
mark rights billing 'FCCPC Patients'"'"' Bill of Rights, illustrated guide (policy, not law) https://fccpc.gov.ng/wp-content/uploads/2023/04/PATIENTS-BILL-OF-RIGHTS-ILLUSTRATED-GUIDE.pdf'
mark rights dignity 'FCCPC Patients'"'"' Bill of Rights, illustrated guide (policy, not law) https://fccpc.gov.ng/wp-content/uploads/2023/04/PATIENTS-BILL-OF-RIGHTS-ILLUSTRATED-GUIDE.pdf'
mark rights quality_care 'FCCPC Patients'"'"' Bill of Rights, illustrated guide (policy, not law) https://fccpc.gov.ng/wp-content/uploads/2023/04/PATIENTS-BILL-OF-RIGHTS-ILLUSTRATED-GUIDE.pdf'
mark rights complain 'National Health Act 2014, Official Gazette No. 145 Vol. 101: s.20 on p. A153, s.30 on p. A156 https://scorecard.prb.org/wp-content/uploads/2019/06/Nigeria-National-Health-Act-2014.pdf'

# ---- messages
# A1.emergency_refused also needs these contacts signed off: emergency
mark messages A1.emergency_refused 'National Health Act 2014, Official Gazette No. 145 Vol. 101: s.20 on p. A153, s.30 on p. A156 https://scorecard.prb.org/wp-content/uploads/2019/06/Nigeria-National-Health-Act-2014.pdf; Lagos State Ministry of Health contact page: '"'"'Emergency Line: 767 / 112'"'"'. Then test-call both. https://lagosministryofhealth.org/contact/; FCCPC Patients'"'"' Bill of Rights, illustrated guide (policy, not law) https://fccpc.gov.ng/wp-content/uploads/2023/04/PATIENTS-BILL-OF-RIGHTS-ILLUSTRATED-GUIDE.pdf'   # TEST-CALL
# A1.detention also needs these contacts signed off: legal_aid
mark messages A1.detention 'FCCPC Patients'"'"' Bill of Rights, illustrated guide (policy, not law) https://fccpc.gov.ng/wp-content/uploads/2023/04/PATIENTS-BILL-OF-RIGHTS-ILLUSTRATED-GUIDE.pdf; Lagos State Public Defender contact page. Then test-call. https://opdlagosstate.org/contact.html'   # TEST-CALL
# A1.generic also needs these contacts signed off: emergency
mark messages A1.generic 'Lagos State Ministry of Health contact page: '"'"'Emergency Line: 767 / 112'"'"'. Then test-call both. https://lagosministryofhealth.org/contact/'   # TEST-CALL
mark messages E.clinical 'MDCN doctor complaint form (asks for an affidavit) https://www.portal.mdcn.gov.ng/doctor-complaint; FCCPC Patients'"'"' Bill of Rights, illustrated guide (policy, not law) https://fccpc.gov.ng/wp-content/uploads/2023/04/PATIENTS-BILL-OF-RIGHTS-ILLUSTRATED-GUIDE.pdf'
# E.handoff also needs these contacts signed off: dsva, emergency
mark messages E.handoff 'Lagos DSVA FAQ and contact pages. Then test-call. https://lagosdsva.org/frequently-asked-questionsfaqs/; Lagos State Ministry of Health contact page: '"'"'Emergency Line: 767 / 112'"'"'. Then test-call both. https://lagosministryofhealth.org/contact/'   # TEST-CALL
# A1.detention_body also needs these contacts signed off: legal_aid
mark messages A1.detention_body 'FCCPC Patients'"'"' Bill of Rights, illustrated guide (policy, not law) https://fccpc.gov.ng/wp-content/uploads/2023/04/PATIENTS-BILL-OF-RIGHTS-ILLUSTRATED-GUIDE.pdf; Lagos State Public Defender contact page. Then test-call. https://opdlagosstate.org/contact.html'   # TEST-CALL
# E.handoff.sexual_violence also needs these contacts signed off: dsva, sarc
mark messages E.handoff.sexual_violence 'Lagos DSVA FAQ and contact pages. Then test-call. https://lagosdsva.org/frequently-asked-questionsfaqs/; Mirabel Centre contact page. Then test-call. https://mirabelcentre.org/contact-us/'   # TEST-CALL
# E.handoff.self_harm also needs these contacts signed off: crisis, emergency
mark messages E.handoff.self_harm 'SURPIN site footer. Hours unconfirmed: MUST be test-called. https://www.surpinng.com/; Lagos State Ministry of Health contact page: '"'"'Emergency Line: 767 / 112'"'"'. Then test-call both. https://lagosministryofhealth.org/contact/'   # TEST-CALL

# ---- asks
mark asks emergency_refused 'National Health Act 2014, Official Gazette No. 145 Vol. 101: s.20 on p. A153, s.30 on p. A156 https://scorecard.prb.org/wp-content/uploads/2019/06/Nigeria-National-Health-Act-2014.pdf; FCCPC Patients'"'"' Bill of Rights, illustrated guide (policy, not law) https://fccpc.gov.ng/wp-content/uploads/2023/04/PATIENTS-BILL-OF-RIGHTS-ILLUSTRATED-GUIDE.pdf'
mark asks detention 'FCCPC Patients'"'"' Bill of Rights, illustrated guide (policy, not law) https://fccpc.gov.ng/wp-content/uploads/2023/04/PATIENTS-BILL-OF-RIGHTS-ILLUSTRATED-GUIDE.pdf; Constitution of Nigeria 1999, ss.34 and 35 https://nigeriarights.gov.ng/files/constitution.pdf'
mark asks abuse 'Constitution of Nigeria 1999, ss.34 and 35 https://nigeriarights.gov.ng/files/constitution.pdf; National Health Act 2014, Official Gazette No. 145 Vol. 101: s.20 on p. A153, s.30 on p. A156 https://scorecard.prb.org/wp-content/uploads/2019/06/Nigeria-National-Health-Act-2014.pdf; FCCPC Patients'"'"' Bill of Rights, illustrated guide (policy, not law) https://fccpc.gov.ng/wp-content/uploads/2023/04/PATIENTS-BILL-OF-RIGHTS-ILLUSTRATED-GUIDE.pdf'
mark asks neglect 'FCCPC Patients'"'"' Bill of Rights, illustrated guide (policy, not law) https://fccpc.gov.ng/wp-content/uploads/2023/04/PATIENTS-BILL-OF-RIGHTS-ILLUSTRATED-GUIDE.pdf; National Health Act 2014, Official Gazette No. 145 Vol. 101: s.20 on p. A153, s.30 on p. A156 https://scorecard.prb.org/wp-content/uploads/2019/06/Nigeria-National-Health-Act-2014.pdf'

echo; uv run python -m app.verify list ng-lagos | head -1
