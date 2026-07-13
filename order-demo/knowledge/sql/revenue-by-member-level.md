---
nl: 按客户会员等级统计销售额
sql: |
  SELECT
    c.member_level,
    COUNT(*) AS order_count,
    SUM(o.total_amount) AS total_revenue
  FROM "orders" o
  JOIN "customers" c
    ON o.customer_id = c.id
  GROUP BY 1
  ORDER BY total_revenue DESC
source: seed
tags:
  - revenue
  - customers
  - member_level
---