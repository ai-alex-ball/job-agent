# Job Agent Prompts - README

## How these prompts fit into the build

### Run ONCE (before the agent goes live)
| File | Purpose |
|------|---------|
| 02_achievement_quantifier.md | Transform your raw CV bullets into quantified power bullets — do this FIRST |
| 04_professional_summary.md | Generate 5 summary options, pick the best one for your profile |
| 07_linkedin_optimizer.md | Rewrite your actual LinkedIn profile to attract inbound recruiters |
| 09_executive_brand.md | Optional — use if repositioning or targeting a big step up |
| 10_career_pivot.md | Optional — use if changing industry or role type |
| 12_career_portfolio.md | Optional — build a portfolio to reference in applications |

### Run AUTOMATICALLY (daily pipeline - every application)
| File | Purpose |
|------|---------|
| 00_master_pipeline_prompt.md | Core agent system prompt — combines scoring, CV tailoring, and cover letter |
| 01_resume_rewriter.md | Full CV rewrite per job (reference version — master prompt handles this) |
| 03_ats_optimizer.md | ATS keyword scoring (reference version — master prompt handles this) |
| 05_cover_letter.md | Cover letter per job (reference version — master prompt handles this) |

### Run ON DEMAND (when triggered by events)
| File | Purpose |
|------|---------|
| 06_salary_negotiation.md | Trigger when you receive an offer |
| 08_behavioral_interview.md | Trigger when an interview is confirmed |
| 11_case_study_prep.md | Trigger when interview confirmed for finance/strategy/consulting roles |

## Getting started

1. Open 02_achievement_quantifier.md in Claude chat
2. Paste your current CV into the placeholder at the bottom
3. Save the output as your master CV
4. Run 04_professional_summary.md with your background details
5. Pick your favourite summary and add it to your master CV
6. You're ready to start building the agent on top of this foundation
