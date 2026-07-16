SET NAMES utf8mb4;
CREATE TABLE IF NOT EXISTS customers (
  id INT PRIMARY KEY,
  customer_no VARCHAR(64) NOT NULL UNIQUE,
  customer_name VARCHAR(128) NOT NULL,
  gender VARCHAR(16) NULL,
  mobile VARCHAR(32) NULL,
  email VARCHAR(128) NULL,
  city VARCHAR(64) NOT NULL,
  region VARCHAR(32) NOT NULL,
  member_level VARCHAR(32) NOT NULL,
  registered_at DATETIME NOT NULL
);

INSERT INTO customers
(id, customer_no, customer_name, gender, mobile, email, city, region, member_level, registered_at)
VALUES
(101, 'CUST-101', '张晨', '男', '13800000001', 'zhangchen@example.com', '上海', '华东', 'GOLD', '2026-01-15 09:00:00'),
(102, 'CUST-102', '李雪', '女', '13800000002', 'lixue@example.com', '北京', '华北', 'SILVER', '2026-02-10 10:30:00'),
(103, 'CUST-103', '王敏', '女', '13800000003', 'wangmin@example.com', '杭州', '华东', 'PLATINUM', '2026-02-18 11:00:00'),
(104, 'CUST-104', '赵磊', '男', '13800000004', 'zhaolei@example.com', '广州', '华南', 'GOLD', '2026-03-05 15:20:00'),
(105, 'CUST-105', '陈静', '女', '13800000005', 'chenjing@example.com', '成都', '西南', 'SILVER', '2026-03-16 16:00:00'),
(106, 'CUST-106', '刘洋', '男', '13800000006', 'liuyang@example.com', '天津', '华北', 'GOLD', '2026-04-01 08:40:00'),
(107, 'CUST-107', '孙浩', '男', '13800000007', 'sunhao@example.com', '南京', '华东', 'PLATINUM', '2026-04-18 14:10:00'),
(108, 'CUST-108', '周婷', '女', '13800000008', 'zhouting@example.com', '深圳', '华南', 'SILVER', '2026-05-02 13:25:00'),
(109, 'CUST-109', '吴倩', '女', '13800000009', 'wuqian@example.com', '武汉', '华中', 'GOLD', '2026-05-20 17:45:00'),
(110, 'CUST-110', '郑凯', '男', '13800000010', 'zhengkai@example.com', '苏州', '华东', 'SILVER', '2026-06-01 09:10:00'),
(111, 'CUST-111', '冯宇', '男', '13800000011', 'fengyu@example.com', '石家庄', '华北', 'GOLD', '2026-06-18 10:10:00'),
(112, 'CUST-112', '何欣', '女', '13800000012', 'hexin@example.com', '佛山', '华南', 'PLATINUM', '2026-06-25 11:30:00');

CREATE TABLE IF NOT EXISTS orders (
  id INT PRIMARY KEY AUTO_INCREMENT,
  order_no VARCHAR(64) NOT NULL UNIQUE,
  customer_id INT NOT NULL,
  product_name VARCHAR(128) NOT NULL,
  product_category VARCHAR(64) NOT NULL,
  unit_price DECIMAL(10,2) NOT NULL,
  quantity INT NOT NULL,
  total_amount DECIMAL(10,2) NOT NULL,
  order_status VARCHAR(32) NOT NULL,
  payment_method VARCHAR(32) NOT NULL,
  region VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL,
  paid_at DATETIME NULL,
  CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) REFERENCES customers(id)
);

INSERT INTO orders
(order_no, customer_id, product_name, product_category, unit_price, quantity, total_amount, order_status, payment_method, region, created_at, paid_at)
VALUES
('ORD-20260601-001', 101, '旗舰手机 X1', '手机数码', 3999.00, 1, 3999.00, 'PAID',      'ALIPAY',   '华东', '2026-06-01 10:15:00', '2026-06-01 10:20:00'),
('ORD-20260603-002', 102, '蓝牙耳机 Air', '手机数码',  299.00, 2,  598.00, 'SHIPPED',   'WECHAT',   '华北', '2026-06-03 14:30:00', '2026-06-03 14:35:00'),
('ORD-20260605-003', 103, '27寸显示器',   '办公设备', 1499.00, 1, 1499.00, 'COMPLETED', 'ALIPAY',   '华东', '2026-06-05 09:00:00', '2026-06-05 09:05:00'),
('ORD-20260608-004', 104, '人体工学椅',   '办公设备',  899.00, 1,  899.00, 'PAID',      'BANKCARD', '华南', '2026-06-08 16:20:00', '2026-06-08 16:25:00'),
('ORD-20260612-005', 105, '机械键盘 K8',  '电脑配件',  399.00, 3, 1197.00, 'CANCELLED', 'ALIPAY',   '西南', '2026-06-12 11:10:00', NULL),
('ORD-20260615-006', 106, '千兆路由器',   '网络设备',  499.00, 2,  998.00, 'COMPLETED', 'WECHAT',   '华北', '2026-06-15 13:40:00', '2026-06-15 13:43:00'),
('ORD-20260701-007', 107, '商务笔记本 Pro', '电脑整机', 6999.00, 1, 6999.00, 'PAID',      'BANKCARD', '华东', '2026-07-01 08:50:00', '2026-07-01 08:55:00'),
('ORD-20260704-008', 108, '无线鼠标 M3',  '电脑配件',  199.00, 4,  796.00, 'SHIPPED',   'WECHAT',   '华南', '2026-07-04 12:00:00', '2026-07-04 12:03:00'),
('ORD-20260707-009', 109, '平板电脑 T11', '手机数码', 2999.00, 1, 2999.00, 'REFUNDED',  'ALIPAY',   '华中', '2026-07-07 15:10:00', '2026-07-07 15:15:00'),
('ORD-20260709-010', 110, '机械硬盘 4TB', '电脑配件',  459.00, 2,  918.00, 'COMPLETED', 'BANKCARD', '华东', '2026-07-09 09:35:00', '2026-07-09 09:40:00'),
('ORD-20260711-011', 111, '高清摄像头',   '电脑配件',  699.00, 1,  699.00, 'PAID',      'WECHAT',   '华北', '2026-07-11 18:25:00', '2026-07-11 18:30:00'),
('ORD-20260712-012', 112, '激光打印机',   '办公设备', 1299.00, 1, 1299.00, 'SHIPPED',   'ALIPAY',   '华南', '2026-07-12 10:45:00', '2026-07-12 10:50:00');
