SELECT *
FROM orders o
JOIN users u ON o.user_id = u.id
WHERE LOWER(u.email) LIKE '%@gmail.com'
  AND o.status NOT IN (SELECT status FROM blocked_statuses)
ORDER BY o.created_at DESC
OFFSET 10000
LIMIT 20;
