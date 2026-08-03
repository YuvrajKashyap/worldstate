# Implementation skill provenance

Skills inspected for this implementation on 2026-07-30:

| Requested skill | Source revision | Result |
| --- | --- | --- |
| `fastapi/fastapi@fastapi` | `95f8322ee1dcda7ceace7b1c4f6c9915b36d748f` | installed; guided lifespan, strict contracts, WebSockets, and official frontend serving |
| `mindrally/skills@computer-vision-opencv` | `05a71308897983093248d719a2ffa1bca61d0768` | installed; guided bounded OpenCV capture and quality handling |
| `supercent-io/skills-template@backend-testing` | unavailable: upstream repository returned not found | not installed |
| `mindrally/skills@python-testing` | `05a71308897983093248d719a2ffa1bca61d0768` | installed audited fallback for backend testing |

The installed security threat-model, security-best-practices, and Jupyter
skills were also applied. The three installed Skills.sh packages reported safe
or low-risk audits with no unresolved warnings at installation time.

Skill packages inform implementation technique; repository tests, pinned
dependencies, generated contracts, and the threat model remain the auditable
source of truth.
