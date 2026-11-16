# Nhặt Được — Đà Nẵng

## Chạy ứng dụng

1. Cài Python 3.10 trở lên.
2. Cài thư viện: `python -m pip install -r requirements.txt`
3. Chạy máy chủ: `python app.py`
4. Mở `http://127.0.0.1:5000` trong trình duyệt.

## Cấu trúc dự án

- `backend/`: máy chủ Flask và phân tích rủi ro cục bộ.
- `frontend/templates/` và `frontend/static/`: giao diện HTML và JavaScript.
- `database/`: schema SQLite và tệp dữ liệu CSDL.
- `tests/`: kiểm thử ứng dụng.
- `app.py` và `init_db.py`: lệnh chạy tương thích ở thư mục gốc.

Không mở trực tiếp `index.html` bằng giao thức `file://`; trang cần máy chủ Flask để đăng nhập và lưu dữ liệu.

CSDL SQLite `danang_lost_found.db` được tạo và cập nhật tự động khi máy chủ khởi động. Để tạo tài khoản quản trị trên CSDL mới, chạy `python init_db.py`; mật khẩu được nhập tương tác và lưu dạng PBKDF2 có salt. Tài khoản quản trị hiện có không bị ghi đè khi khởi tạo lại.

Có thể cấu hình `DATABASE_PATH`, `PORT` và `SESSION_SECRET` qua biến môi trường. Hãy đặt `SESSION_SECRET` ổn định, bật HTTPS và đặt `COOKIE_SECURE=true` khi triển khai ngoài máy cá nhân. Máy chủ mặc định chỉ lắng nghe `127.0.0.1`.

## Quyền và xác minh

- Mọi tài khoản người dùng đều có thể đăng cả tin mất lẫn tin nhặt được và phản hồi tin của người khác; khi đăng ký không cần chọn loại người dùng.
- Khi báo mất đồ, người dùng chỉ cần chọn quận/khu vực hoặc nhập tên đường/khu vực; có thể cung cấp cả hai để người khác dễ tìm hơn.
- Mỗi tin cần một đặc điểm riêng. Đặc điểm này không xuất hiện trong API tin công khai.
- Số điện thoại không hiển thị công khai; chỉ được chia sẻ cho hai bên sau khi người đăng chấp nhận phản hồi.
- Khi phản hồi tin mất đồ, người nhặt có thể đề xuất thời gian và địa điểm hẹn; cảnh báo nguy hiểm xuất hiện nếu giờ hẹn ngoài 06:00–22:00 và người đề xuất không xác nhận địa điểm công cộng, đông người. Đây là xác nhận của người dùng, không phải kiểm chứng tự động.
- Bộ sàng lọc rủi ro chạy cục bộ, so sánh từ khóa và dấu hiệu yêu cầu lặp lại; không gửi dữ liệu tới dịch vụ AI bên ngoài. Chỉ người đăng tin và admin xem được điểm/lý do.
- Điểm rủi ro chỉ hỗ trợ đánh giá, không xác minh danh tính và không tự động duyệt/từ chối yêu cầu. Hai bên cần đối chiếu trực tiếp trước khi trao đồ.
- Admin có thể quản lý tài khoản, ẩn tin và xem yêu cầu xác minh.

Đây là ứng dụng mẫu chạy cục bộ, chưa có xác thực email/SMS, quy trình khôi phục mật khẩu hay cấu hình triển khai Internet đầy đủ.
