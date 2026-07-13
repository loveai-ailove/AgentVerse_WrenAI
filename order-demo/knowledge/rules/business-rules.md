## 业务口径

- revenue 指订单总金额，统一使用 `orders.total_amount`
- order count 指订单行数，统一使用 `COUNT(*)`
- 时间分析默认使用 `orders.created_at`，不是 `orders.paid_at`

## 客户口径

- 客户维度来自 `customers`
- 客户地区使用 `customers.region`
- 会员等级使用 `customers.member_level`
- 订单表中的 `customer_id` 关联 `customers.id`

## 状态约定

- `PAID` 表示已支付未发货
- `SHIPPED` 表示已发货
- `COMPLETED` 表示已完成
- `CANCELLED` 表示已取消，通常 `paid_at` 为空
- `REFUNDED` 表示已退款，历史金额仍保留在 `total_amount`