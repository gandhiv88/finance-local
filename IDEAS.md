# Future Improvement Ideas for Finance Local

## ML/Automation

- **ML Confidence UI Page**
  - Prediction Playground: Enter a transaction description (and optionally merchant) and see the predicted category, confidence score, and top-k alternatives.
  - Bulk Preview: Preview ML predictions and confidence for all uncategorized transactions, with an option to accept or override.
  - Training Metrics Dashboard: Show model accuracy, per-category support, last trained date, and number of examples.

- **Active Learning**
  - Let users correct ML predictions and use those corrections to trigger retraining.

- **Auto-retrain Scheduling**
  - Option to auto-retrain the model when enough new labeled data is available.

- **Explainability**
  - Show which words or features contributed most to the ML prediction.

## User Experience

- **Onboarding Wizard**
  - Guide new users through connecting accounts, seeding categories, and uploading their first statement.

- **Category Management**
  - Drag-and-drop category hierarchy, merge categories, or color coding.

- **Undo/Redo**
  - Allow users to undo bulk actions or recategorizations.

## Reporting/Insights

- **Trend Analysis**
  - Visualize spending/income trends, category drift, or recurring merchants.

- **Budget Suggestions**
  - Suggest budgets based on historical spending.

- **Alerts**
  - Notify users of overspending, unusual transactions, or ML confidence below a threshold.

## Integrations

- **Import/Export**
  - Support for more bank formats, CSV export, or integration with other finance tools.

- **API Tokens**
  - Allow secure API access for power users.

## Performance/Robustness

- **Background Jobs**
  - Move heavy ML training or recategorization to background tasks.

- **Audit Log**
  - Track changes to transactions and categories for transparency.

## Data Visualization & Charts

- **Spending Over Time**
  - Line Chart: Monthly spending/income trends.
  - Area Chart: Cumulative spend vs. income.

- **Category Breakdown**
  - Pie/Donut Chart: Proportion of spending by category for a selected period.
  - Stacked Bar Chart: Category spend per month.

- **Budget vs. Actual**
  - Bar Chart: Compare budgeted vs. actual spend per category.
  - Gauge Chart: Show how close you are to budget limits.

- **Merchant Analysis**
  - Bar Chart: Top merchants by spend.
  - Scatter Plot: Transaction count vs. total spend per merchant.

- **ML Confidence Visualization**
  - Histogram: Distribution of ML confidence scores for predictions.
  - Bar Chart: Number of transactions auto-categorized by ML, by confidence band.

- **Cash Flow**
  - Line or Area Chart: Inflow vs. outflow over time.

- **Recurring Transactions**
  - Timeline or Calendar View: Visualize recurring bills/subscriptions.

- **Custom Insights**
  - Alert/Warning Chart: Visualize overspending, spikes, or anomalies flagged by the system.

---

*Add more ideas as you