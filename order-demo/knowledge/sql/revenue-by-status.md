---
nl: 按订单状态统计销售额和订单数
sql: |
  SELECT
    order_status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_revenue
  FROM "orders"
  GROUP BY 1
  ORDER BY total_revenue DESC
source: seed
tags:
  - revenue
  - status
  - orders
---