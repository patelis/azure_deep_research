targetScope = 'resourceGroup'

// Monthly cost budget with email alerts. NOTE: budgets are alert-only — they notify, they do
// not stop spend. Combine with low deployment capacity + the app's per-key daily run cap.

@description('Monthly budget amount (billing currency).')
param amount int = 20

@description('Budget start date (first of a month), format yyyy-MM-dd.')
param startDate string

@description('Budget end date, format yyyy-MM-dd.')
param endDate string = '2035-12-01'

@description('Emails notified at threshold breaches.')
param contactEmails array

@description('Budget resource name.')
param budgetName string = 'rg-monthly-budget'

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: budgetName
  properties: {
    category: 'Cost'
    amount: amount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: startDate
      endDate: endDate
    }
    notifications: {
      actual_50: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        contactEmails: contactEmails
        thresholdType: 'Actual'
      }
      actual_80: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        contactEmails: contactEmails
        thresholdType: 'Actual'
      }
      actual_100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        contactEmails: contactEmails
        thresholdType: 'Actual'
      }
      forecast_100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        contactEmails: contactEmails
        thresholdType: 'Forecasted'
      }
    }
  }
}
