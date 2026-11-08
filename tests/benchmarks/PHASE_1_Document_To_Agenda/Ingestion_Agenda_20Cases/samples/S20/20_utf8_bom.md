# Windows UTF8 BOM

## Mục tiêu kiểm thử mã hóa

Nhóm cần thống nhất cách bảo toàn dấu tiếng Việt trong luồng tải tài liệu vào ứng dụng. Ghi chú này được lưu dưới dạng Markdown UTF-8 có BOM, giống một số tệp được tạo bằng trình soạn thảo trên Windows. Nội dung tập trung vào một quyết định về bảo toàn văn bản; những ví dụ tên riêng, câu mô tả và dấu câu phía dưới chỉ là dữ liệu để xem chuỗi ký tự có bị thay đổi hay không.

## Nội dung cần quyết định

- Chốt cách bảo toàn dấu tiếng Việt khi tải tệp.

## Hiện trạng cần xem xét

Một tài liệu tiếng Việt có thể trông đúng trong trình soạn thảo nhưng bị mất dấu hoặc xuất hiện ký tự lạ sau khi tải vào ứng dụng. Khi đọc agenda được tạo từ văn bản đó, người dùng sẽ khó xác định tên người và ý nghĩa của câu. Nhóm chưa chốt cách nhận diện và xử lý dấu BOM trong bước đọc tệp. Vấn đề cần bàn là giữ nguyên nội dung tiếng Việt qua luồng tải lên, không phải đổi ngôn ngữ toàn bộ giao diện.

## Các chuỗi dùng đối chiếu

Nhóm chuẩn bị các tên giả lập như Hà, Hưng, Thảo, Đặng Minh và Nguyễn Thu để đối chiếu trước và sau khi tải tệp. Một câu khác dùng các từ cuộc họp, dữ liệu, quyền truy cập, bộ lọc tiếng ồn và người phụ trách. Những chuỗi này có nhiều dấu thanh và ký tự đặc trưng như ă, â, đ, ê, ô, ơ, ư. Chúng không phải danh sách người cần phân công công việc hoặc những chủ đề agenda cần tách riêng.

## Phạm vi quyết định

Chốt cách bảo toàn dấu tiếng Việt khi tải tệp. Nhóm cần xem phần văn bản đã đọc có khớp với tài liệu gốc hay không và xác định cách xử lý khi đầu tệp có BOM. Việc đối chiếu nên thực hiện trên cùng một tệp để tránh nhầm với thay đổi do người viết chỉnh sửa. Các khác biệt giữa chữ hoa, chữ thường và khoảng trắng được ghi nhận như thông tin hỗ trợ cho cùng vấn đề bảo toàn văn bản.

## Những việc đã chuẩn bị

Tệp mẫu và ảnh chụp nội dung gốc đã được chuẩn bị, các thành viên cũng đã xác nhận có thể mở tệp trong trình soạn thảo của mình. Đây là việc đã hoàn thành trước cuộc họp. Không có đề xuất thay đổi font, xây dựng trình soạn thảo mới hoặc thêm hệ thống dịch thuật. Tài liệu chỉ dùng các ví dụ đó để giúp nhóm nhận ra lỗi mã hóa nếu nó xuất hiện trong bước tải lên.

## Kết quả cần ghi nhận

Sau cuộc họp, ghi lại quy tắc đọc tệp tiếng Việt và cách xác nhận nội dung được giữ nguyên. Nếu vẫn thấy mất dấu ở một bước, cần ghi rõ vị trí quan sát và ví dụ liên quan thay vì kết luận chung rằng toàn bộ ứng dụng không hỗ trợ tiếng Việt. Các ghi chú này là chi tiết của một quyết định duy nhất. Tiêu đề agenda được tạo bằng ngôn ngữ theo cấu hình của tính năng, nhưng văn bản nguồn phải còn nguyên dấu để có thể hiểu đúng nội dung.
