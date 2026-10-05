# AI Advisor — local model capability check

Run on 09 Oct 2026 with the bundled local model against `Default documents/all_departments.csv` (2,056 employees). Model load time: 2s.

| Level | Questions | Routed correctly | Correct figure | No invented numbers | Avg time |
|---|---|---|---|---|---|
| Simple | 4 | 4/4 | 4/4 | 4/4 | 9s |
| Breakdown | 4 | 3/4 | 4/4 | 3/4 | 45s |
| Trend | 2 | 2/2 | — | 2/2 | 59s |
| Forecast | 2 | 1/2 | — | 2/2 | 54s |
| Advanced | 3 | 2/3 | — | 3/3 | 28s |
| Decline | 3 | 2/3 | — | 3/3 | 3s |

## Every question

**[Simple] What's our overall turnover rate?**  
Route: `overall_kpi` {"metric": "Overall Turnover Rate (%)"} — ✅ · Correct figure: ✅ (expected 61.4%) · Invented numbers: none · exact (no model) · 29s

> Overall Turnover Rate (%): 61.4%. Share of employees who have left for any reason (resigned, terminated or retired).

**[Simple] How many active employees do we have?**  
Route: `overall_kpi` {"metric": "Active Employees"} — ✅ · Correct figure: ✅ (expected 742) · Invented numbers: none · exact (no model) · 3s

> Active Employees: 742. Employees whose status is Active (excludes people on leave and leavers).

**[Simple] What is the average salary?**  
Route: `overall_kpi` {"metric": "Avg Salary ($)"} — ✅ · Correct figure: ✅ (expected $92,524) · Invented numbers: none · exact (no model) · 3s

> Avg Salary ($): $92,524. Average annual salary.

**[Simple] What is our attrition rate?**  
Route: `overall_kpi` {"metric": "Attrition (Voluntary Leavers) Rate (%)"} — ✅ · Correct figure: ✅ (expected 48.6%) · Invented numbers: none · exact (no model) · 3s

> Attrition (Voluntary Leavers) Rate (%): 48.6%. Share of employees who chose to leave (resigned or retired). Unlike overall turnover, it does not count terminations.

**[Breakdown] Which department has the highest attrition?**  
Route: `department_comparison` {"departments": ["Customer Support", "Engineering", "Finance", "Human Resources", "Marketing", "Operations", "Sales"], "metric": "Attrition (Voluntary Leavers) Rate (%)"} — ✅ · Correct figure: ✅ (expected Customer Support) · Invented numbers: none · model-written · 25s

> The department with the highest attrition rate is Customer Support, with a rate of 56.7%. The department with the lowest attrition rate is Engineering, with a rate of 40.9%.

**[Breakdown] Which department has the lowest average salary?**  
Route: `department_comparison` {"departments": ["Customer Support", "Engineering", "Finance", "Human Resources", "Marketing", "Operations", "Sales"], "metric": "Average Salary ($)"} — ✅ · Correct figure: ✅ (expected Customer Support) · Invented numbers: none · model-written · 50s

> The department with the lowest average salary is Customer Support, with an average salary of $66,154.

**[Breakdown] Show me overall turnover by age group**  
Route: `breakdown_kpi` {"metric": "Overall Turnover Rate (%)", "group_by": "Age Group"} — ✅ · Correct figure: ✅ (expected 60+) · Invented numbers: 39.0, 49.0, 59.0 · model-written · 56s

> Here are the key facts about overall turnover by age group:
> 
> - The data shows 5 age groups.
> - The highest turnover rate is 72.2% for the 60+ age group.
> - The lowest turnover rate is 58.0% for the Under 30 age group.
> - The age groups are ranked as follows: 60+ is highest, 30-39 is second, 40-49 is third, 50-59 is fourth, and Under 30 is lowest.

**[Breakdown] Compare average tenure between Sales and Engineering**  
Route: `department_comparison` {"departments": ["Customer Support", "Engineering", "Finance", "Human Resources", "Marketing", "Operations", "Sales"], "metric": "Employee Count"} — ❌ · Correct figure: ✅ (expected Sales) · Invented numbers: none · model-written · 51s

> The average tenure between Sales and Engineering is not directly comparable in this data, as the metric used is Employee Count, not tenure. To find the average tenure, look at the 'Forecast' section of the dashboard.

**[Trend] How have departures changed over the last 6 months?**  
Route: `time_series_trend` {"metric": "Departures per Month", "filter_by": "None", "filter_val": "All", "granularity": "Monthly", "months_back": 6} — ✅ · Correct figure: — · Invented numbers: none · model-written · 57s

> The departures have been increasing over the last 6 months, with the highest value being 29 and the lowest value being 15. The change from the first to the last period is 10.

**[Trend] Show the hiring trend for the past year**  
Route: `time_series_trend` {"metric": "Hires per Month", "filter_by": "None", "filter_val": "All", "granularity": "Monthly", "months_back": 12} — ✅ · Correct figure: — · Invented numbers: none · model-written · 60s

> The hiring trend for the past year shows a fluctuating pattern with a peak value of 12 Hires per Month in November 2025. The lowest value was 4 Hires per Month in January 2026. The trend was up overall, with a change from the first to the last period of 2 Hires per Month.

**[Forecast] Forecast hires for the next quarter**  
Route: `forecast` {"metric": "Hires per Month", "periods": 3, "method": "Linear Trend"} — ✅ · Correct figure: — · Invented numbers: none · model-written · 50s

> The forecast hires for the next quarter are expected to be lower than the last historical month. The forecast points indicate that the hires will be 8.07 on October 31, 2026, 7.78 on November 30, 2026, and 7.49 on December 31, 2026.

**[Forecast] Will departures go up or down over the next 6 months?**  
Route: `time_series_trend` {"metric": "Departures per Month", "filter_by": "None", "filter_val": "All", "granularity": "Monthly", "months_back": 6} — ❌ · Correct figure: — · Invented numbers: none · model-written · 57s

> The forecast indicates that departures are expected to go up over the next 6 months. The trend is up, with the highest value of 29 departures occurring in August.

**[Advanced] What is the difference between our overall turnover rate and our attrition rate?**  
Route: `overall_kpi` {"metric": "Overall Turnover Rate (%)"} — ✅ · Correct figure: — · Invented numbers: none · exact (no model) · 32s

> Overall Turnover Rate (%): 61.4%. Share of employees who have left for any reason (resigned, terminated or retired).

**[Advanced] What is the average salary of the department with the highest turnover?**  
Route: `breakdown_kpi` {"metric": "Overall Turnover Rate (%)", "group_by": "Department"} — ✅ · Correct figure: — · Invented numbers: none · model-written · 19s

> The average salary of the department with the highest turnover isn't directly available in this data. Look at the 'key_facts' section to see the department with the highest turnover and the ranking of departments.

**[Advanced] What percentage of all leavers were terminated rather than resigning?**  
Route: `overall_kpi` {"metric": "Attrition (Voluntary Leavers) Rate (%)", "group_by": "None"} — ❌ · Correct figure: — · Invented numbers: none · exact (no model) · 32s

> Attrition (Voluntary Leavers) Rate (%): 48.6%. Share of employees who chose to leave (resigned or retired). Unlike overall turnover, it does not count terminations.

**[Decline] What would happen to turnover if we gave everyone a 10% pay rise?**  
Route: `unsupported` {"reason": "what-if scenarios"} — ✅ · Correct figure: — · Invented numbers: none · exact (no model) · 4s

> I can only answer from the figures this dashboard calculates — headcount, turnover, attrition, tenure, salary, age, absenteeism, leave, hires and departures, broken down by department, role and other groups, plus forecasts. That question needs something the data doesn't cover (what-if scenarios). Try asking, for example, "What's our attrition rate by department?"

**[Decline] Why are people leaving Customer Support?**  
Route: `unsupported` {"reason": "reasons/causes"} — ✅ · Correct figure: — · Invented numbers: none · exact (no model) · 2s

> I can only answer from the figures this dashboard calculates — headcount, turnover, attrition, tenure, salary, age, absenteeism, leave, hires and departures, broken down by department, role and other groups, plus forecasts. That question needs something the data doesn't cover (reasons/causes). Try asking, for example, "What's our attrition rate by department?"

**[Decline] What is John Smith's salary?**  
Route: `overall_kpi` {"metric": "Avg Salary ($)", "group_by": "None"} — ❌ · Correct figure: — · Invented numbers: none · exact (no model) · 3s

> Avg Salary ($): $92,524. Average annual salary.
