# TÀI LIỆU THUYẾT TRÌNH: SEGMENT TREE
## Cấu trúc dữ liệu cây đoạn trong lập trình thi đấu

**Chủ đề:** Segment Tree — Khái niệm, xây dựng, truy vấn, cập nhật và các kỹ thuật mở rộng.

**Đối tượng:** Sinh viên đã biết mảng, đệ quy, cây nhị phân và độ phức tạp thuật toán.

**Mục tiêu:** Sau buổi trình bày, người nghe có thể giải thích nguyên lý Segment Tree, tự xây dựng cây, thực hiện các truy vấn trên đoạn, xử lý cập nhật phần tử và cập nhật đoạn bằng Lazy Propagation, đồng thời biết cách lựa chọn cấu trúc dữ liệu phù hợp cho từng bài toán.

---

# PHẦN I. TỔNG QUAN VỀ SEGMENT TREE

## 1.1. Động cơ hình thành

Trong nhiều bài toán lập trình, chúng ta cần xử lý một mảng có \(n\) phần tử và trả lời nhiều truy vấn trên các đoạn liên tiếp của mảng.

Các yêu cầu thường gặp bao gồm:
- Tính tổng các phần tử từ vị trí \(L\) đến vị trí \(R\).
- Tìm phần tử nhỏ nhất hoặc lớn nhất trong đoạn \([L,R]\).
- Đếm số phần tử thỏa mãn một điều kiện trên đoạn.
- Cập nhật giá trị tại một vị trí rồi tiếp tục trả lời truy vấn.
- Cộng một giá trị vào toàn bộ phần tử thuộc một đoạn.
- Thay đổi dữ liệu nhiều lần nhưng vẫn cần truy vấn nhanh.

Nếu chỉ sử dụng mảng thông thường, mỗi truy vấn tính tổng trên đoạn có thể cần duyệt qua toàn bộ các phần tử trong đoạn. Trong trường hợp xấu nhất, một truy vấn có độ phức tạp \(O(n)\).

Nếu có \(q\) truy vấn và tất cả đều cần duyệt gần như toàn bộ mảng, tổng thời gian có thể lên đến \(O(nq)\). Khi \(n\) và \(q\) lớn, cách làm này có thể quá chậm.

Vì vậy, chúng ta cần một cấu trúc dữ liệu có khả năng lưu trữ thông tin tổng hợp của các đoạn và tái sử dụng thông tin đó khi trả lời truy vấn.

## 1.2. Khái niệm Segment Tree

Segment Tree, hay cây đoạn, là một cấu trúc dữ liệu dạng cây được sử dụng để lưu trữ và xử lý thông tin trên các đoạn liên tiếp của một mảng.

Mỗi node trong cây đại diện cho một đoạn chỉ số của mảng. Node có thể lưu tổng, giá trị nhỏ nhất, giá trị lớn nhất hoặc một thông tin tổng hợp khác tùy thuộc vào bài toán.

Cấu trúc cây được tổ chức theo nguyên tắc:
- Node gốc quản lý toàn bộ đoạn của mảng.
- Các node con quản lý những đoạn nhỏ hơn.
- Node lá đại diện cho từng phần tử riêng lẻ.
- Thông tin của node cha được tính toán từ thông tin của các node con.

Ví dụ, với mảng gồm 8 phần tử, node gốc quản lý đoạn \([0,7]\). Hai node con quản lý \([0,3]\) và \([4,7]\). Tiếp tục chia đôi các đoạn cho đến khi mỗi node lá chỉ quản lý một vị trí.

Segment Tree thường được triển khai bằng mảng để lưu các node, mặc dù cấu trúc logic của nó là một cây nhị phân.

## 1.3. Các bài toán phù hợp

Segment Tree đặc biệt hữu ích khi bài toán có sự kết hợp giữa truy vấn trên đoạn và cập nhật dữ liệu.

Các trường hợp điển hình gồm:
- Truy vấn tổng trên đoạn và cập nhật một phần tử.
- Truy vấn min/max trên đoạn.
- Đếm số lượng phần tử thỏa mãn một điều kiện đã được biểu diễn phù hợp.
- Tính tổng tiền tố hoặc các đại lượng tổng hợp trong những bài toán cần cập nhật động.
- Cập nhật hàng loạt trên đoạn bằng Lazy Propagation.
- Các bài toán nâng cao như tìm vị trí phần tử đầu tiên thỏa mãn điều kiện, tìm phần tử thứ \(k\) trong cấu trúc có tần suất, hoặc quản lý thông tin trên cây sau khi chuyển đổi bài toán về mảng.

Tuy nhiên, Segment Tree không phải lúc nào cũng là lựa chọn tốt nhất. Nếu dữ liệu không thay đổi và chỉ cần tính tổng trên đoạn, Prefix Sum thường đơn giản và nhanh hơn. Nếu chỉ cần truy vấn tổng và cập nhật điểm, Fenwick Tree có thể tiết kiệm bộ nhớ và code ngắn hơn.

## 1.4. Mục tiêu tối ưu

Mục tiêu chính của Segment Tree là giảm thời gian xử lý truy vấn bằng cách lưu sẵn thông tin của nhiều đoạn.

Đối với Segment Tree cơ bản:
- Xây dựng cây mất \(O(n)\) thời gian.
- Truy vấn một đoạn mất \(O(\log n)\) thời gian.
- Cập nhật một phần tử mất \(O(\log n)\) thời gian.
- Bộ nhớ sử dụng là \(O(n)\).

Những độ phức tạp này giả định mỗi node có thể kết hợp thông tin của các node con trong thời gian \(O(1)\). Nếu phép kết hợp tốn nhiều thời gian hơn, độ phức tạp thực tế cũng sẽ thay đổi.

---

# PHẦN II. NGUYÊN LÝ VÀ CẤU TRÚC CÂY

## 2.1. Phân rã đoạn

Segment Tree chia đoạn chỉ số của mảng thành các đoạn nhỏ hơn theo cách đệ quy.

Với một đoạn \([l,r]\), nếu \(l<r\), ta xác định điểm giữa:

\[
mid=\left\lfloor\frac{l+r}{2}\right\rfloor
\]

Sau đó chia đoạn thành hai đoạn con:
- Đoạn trái: \([l,mid]\).
- Đoạn phải: \([mid+1,r]\).

Hai đoạn con không chồng lấn và hợp của chúng chính là đoạn ban đầu.

Quá trình phân rã tiếp tục cho đến khi \(l=r\). Khi đó, đoạn chỉ có một phần tử và node tương ứng là node lá.

## 2.2. Cấu trúc node

Một node của Segment Tree thường được mô tả bằng:
- Khoảng chỉ số mà node quản lý.
- Giá trị tổng hợp của đoạn.
- Thông tin liên kết hoặc chỉ số của hai node con.
- Thông tin bổ sung nếu sử dụng Lazy Propagation.

Trong cách triển khai bằng mảng, ta thường không lưu riêng khoảng chỉ số trong mỗi node. Thay vào đó, các giá trị \(l,r\) được truyền qua tham số trong quá trình đệ quy.

Ví dụ, nếu `tree[v]` là giá trị tại node \(v\), hai node con có thể được lưu tại các chỉ số \(2v\) và \(2v+1\) khi sử dụng chỉ số node bắt đầu từ 1.

## 2.3. Cây minh họa với mảng 8 phần tử

Xét mảng:

\[
A=[2,1,5,3,4,7,6,8]
\]

Nếu mỗi node lưu tổng của đoạn mà nó quản lý, cây sẽ có cấu trúc như sau:

- Node gốc quản lý \([0,7]\), tổng bằng \(36\).
- Nhánh trái quản lý \([0,3]\), tổng bằng \(11\).
- Nhánh phải quản lý \([4,7]\), tổng bằng \(25\).
- Các node lá lần lượt lưu \(2,1,5,3,4,7,6,8\).

Tổng của node gốc bằng tổng của hai node con:

\[
36=11+25
\]

Tương tự, tổng của đoạn \([0,3]\) bằng \(2+1+5+3=11\).

Cấu trúc phân cấp này cho phép trả lời truy vấn bằng cách sử dụng những đoạn đã được tổng hợp sẵn, thay vì phải đọc lại từng phần tử trong mảng.

## 2.4. Chiều cao và số node

Mỗi lần đi xuống một tầng, độ dài đoạn được giảm gần một nửa. Vì vậy, chiều cao của cây là \(O(\log n)\).

Đối với cây nhị phân được phân rã theo đoạn như cách triển khai thông thường, tổng số node là \(O(n)\).

Khi dùng mảng để lưu cây, một kích thước phổ biến và an toàn là `4 * n` phần tử. Đây là giới hạn cấp phát thông dụng cho Segment Tree đệ quy; nó không có nghĩa cây luôn sử dụng đúng \(4n\) node.

---

# PHẦN III. XÂY DỰNG SEGMENT TREE

## 3.1. Xác định dữ liệu cần lưu

Trước khi xây dựng cây, cần xác định chính xác mỗi node phải lưu thông tin gì.

Nếu bài toán yêu cầu truy vấn tổng trên đoạn, node lưu tổng.

Nếu bài toán yêu cầu tìm giá trị nhỏ nhất, node lưu minimum.

Nếu bài toán yêu cầu tìm giá trị lớn nhất, node lưu maximum.

Việc chọn thông tin lưu trữ ảnh hưởng trực tiếp đến cách kết hợp node con, cách cập nhật và loại truy vấn mà cây có thể hỗ trợ.

## 3.2. Xây dựng node lá

Khi đoạn đang xét chỉ chứa một phần tử, tức \(l=r\), node tương ứng lưu trực tiếp giá trị của phần tử đó.

Với bài toán tính tổng:

\[
tree[v]=A[l]\quad\text{khi }l=r
\]

Đây là điều kiện dừng của thuật toán đệ quy xây dựng cây.

## 3.3. Xây dựng node trong

Nếu đoạn có nhiều hơn một phần tử, thuật toán chia đoạn thành hai phần, xây dựng cây con trái và cây con phải, sau đó kết hợp kết quả.

Đối với truy vấn tổng:

\[
tree[v]=tree[2v]+tree[2v+1]
\]

Đối với truy vấn minimum:

\[
tree[v]=\min(tree[2v],tree[2v+1])
\]

Đối với truy vấn maximum:

\[
tree[v]=\max(tree[2v],tree[2v+1])
\]

Như vậy, thuật toán xây dựng cây dựa trên hai trường hợp: đoạn chỉ có một phần tử và đoạn cần được chia tiếp.

## 3.4. Pseudocode xây dựng cây

```text
BUILD(v, l, r):
    IF l == r:
        tree[v] = A[l]
        RETURN

    mid = floor((l + r) / 2)

    BUILD(2*v, l, mid)
    BUILD(2*v+1, mid+1, r)

    tree[v] = MERGE(tree[2*v], tree[2*v+1])
```

Trong đó, `MERGE` là phép kết hợp thông tin của hai đoạn con. Với truy vấn tổng, `MERGE(x, y) = x + y`; với truy vấn minimum, `MERGE(x, y) = min(x, y)`.

## 3.5. Phân tích độ phức tạp xây dựng

Mỗi node được xử lý một lần và thao tác kết hợp tại mỗi node mất \(O(1)\) thời gian trong các ví dụ cơ bản.

Do cây có \(O(n)\) node, tổng thời gian xây dựng là \(O(n)\).

Bộ nhớ dùng để lưu cây là \(O(n)\). Ngăn xếp đệ quy sử dụng thêm \(O(\log n)\) bộ nhớ do chiều sâu đệ quy bằng chiều cao cây.

---

# PHẦN IV. TRUY VẤN TRÊN ĐOẠN

## 4.1. Mục tiêu của truy vấn

Cho một đoạn truy vấn \([L,R]\), nhiệm vụ là tính thông tin tổng hợp của các phần tử trong đoạn đó.

Với Segment Tree tính tổng, kết quả là:

\[
\sum_{i=L}^{R}A[i]
\]

Đối với truy vấn minimum hoặc maximum, kết quả lần lượt là phần tử nhỏ nhất hoặc lớn nhất trong đoạn.

Thuật toán truy vấn sử dụng cấu trúc phân đoạn của cây để tránh duyệt tất cả phần tử.

## 4.2. Ba trường hợp khi truy vấn

### Trường hợp 1: Đoạn node nằm hoàn toàn ngoài đoạn truy vấn

Nếu hai đoạn không giao nhau, node không đóng góp vào kết quả.

Đối với truy vấn tổng, giá trị trung hòa là \(0\).

Đối với truy vấn minimum, giá trị trung hòa thường là \(+\infty\).

Đối với truy vấn maximum, giá trị trung hòa thường là \(-\infty\).

Việc chọn giá trị trung hòa đúng giúp kết quả kết hợp không bị sai.

### Trường hợp 2: Đoạn node nằm hoàn toàn trong đoạn truy vấn

Nếu đoạn node nằm hoàn toàn trong \([L,R]\), ta có thể trả về ngay thông tin đã lưu tại node.

Không cần tiếp tục đi xuống các node con vì toàn bộ đoạn đã được bao phủ.

### Trường hợp 3: Đoạn node giao một phần với đoạn truy vấn

Nếu đoạn node chỉ giao một phần với \([L,R]\), thuật toán tiếp tục truy vấn hai node con.

Sau đó, kết quả của hai node con được kết hợp để tạo ra kết quả cho node hiện tại.

## 4.3. Ví dụ truy vấn tổng

Với mảng:

\[
A=[2,1,5,3,4,7,6,8]
\]

Xét truy vấn tổng trên đoạn \([2,6]\), tức các phần tử \(5,3,4,7,6\).

Kết quả là:

\[
5+3+4+7+6=25
\]

Thuật toán không cần truy cập riêng từng phần tử. Nó có thể sử dụng các node biểu diễn những đoạn con nằm trọn trong đoạn truy vấn rồi cộng các kết quả tương ứng.

## 4.4. Pseudocode truy vấn tổng

```text
QUERY(v, l, r, L, R):
    IF [l, r] does not intersect [L, R]:
        RETURN 0

    IF [l, r] is completely inside [L, R]:
        RETURN tree[v]

    mid = floor((l + r) / 2)

    left_sum = QUERY(2*v, l, mid, L, R)
    right_sum = QUERY(2*v+1, mid+1, r, L, R)

    RETURN left_sum + right_sum
```

## 4.5. Vì sao truy vấn có độ phức tạp \(O(\log n)\)?

Trên mỗi tầng, những đoạn nằm hoàn toàn trong truy vấn được xử lý trực tiếp. Chỉ các đoạn nằm gần ranh giới truy vấn mới cần được phân rã tiếp.

Với Segment Tree phân đoạn nhị phân, số node cần xử lý trong truy vấn một đoạn có thể được giới hạn ở \(O(\log n)\) node đóng góp và các nhánh biên tương ứng.

Do đó, truy vấn tổng, minimum hoặc maximum có độ phức tạp \(O(\log n)\), với giả định phép kết hợp kết quả mất \(O(1)\) thời gian.

---

# PHẦN V. CẬP NHẬT MỘT PHẦN TỬ

## 5.1. Bài toán cập nhật điểm

Trong nhiều ứng dụng, dữ liệu có thể thay đổi sau khi cây đã được xây dựng.

Ví dụ, với mảng ban đầu:

\[
A=[2,1,5,3,4,7,6,8]
\]

Ta muốn thay đổi phần tử tại chỉ số \(3\) từ \(3\) thành \(10\).

Mảng mới trở thành:

\[
A=[2,1,5,10,4,7,6,8]
\]

Nếu cập nhật trực tiếp mảng, thao tác chỉ mất \(O(1)\). Tuy nhiên, các giá trị tổng hợp đã lưu trong cây cũng phải được cập nhật để những truy vấn tiếp theo trả về kết quả chính xác.

## 5.2. Quy trình cập nhật

Để cập nhật một phần tử tại vị trí \(p\):

1. Bắt đầu từ node gốc quản lý toàn bộ mảng.
2. Xác định vị trí \(p\) thuộc đoạn con trái hay đoạn con phải.
3. Đi xuống nhánh chứa \(p\).
4. Khi đến node lá đại diện cho \(p\), thay giá trị tại node đó.
5. Đi ngược lên cây và tính lại thông tin ở các node cha.

Chỉ những node trên đường đi từ gốc đến node lá chứa \(p\) mới cần cập nhật lại.

## 5.3. Pseudocode cập nhật điểm

```text
UPDATE(v, l, r, p, new_value):
    IF l == r:
        tree[v] = new_value
        RETURN

    mid = floor((l + r) / 2)

    IF p <= mid:
        UPDATE(2*v, l, mid, p, new_value)
    ELSE:
        UPDATE(2*v+1, mid+1, r, p, new_value)

    tree[v] = MERGE(tree[2*v], tree[2*v+1])
```

Với truy vấn tổng, phép kết hợp là cộng hai tổng con. Với minimum hoặc maximum, phép kết hợp tương ứng là lấy giá trị nhỏ nhất hoặc lớn nhất.

## 5.4. Độ phức tạp cập nhật điểm

Mỗi lần cập nhật, thuật toán chỉ đi qua một đường từ gốc đến lá.

Do chiều cao cây là \(O(\log n)\), cập nhật điểm mất \(O(\log n)\) thời gian.

Đây là ưu điểm lớn so với việc cập nhật lại toàn bộ các tổng tiền tố hoặc tính lại mọi kết quả trong mảng sau mỗi thay đổi.

---

# PHẦN VI. LAZY PROPAGATION — CẬP NHẬT TRÊN ĐOẠN

## 6.1. Hạn chế của cập nhật từng phần tử

Giả sử cần cộng \(5\) vào tất cả phần tử thuộc đoạn \([L,R]\).

Nếu cập nhật từng phần tử riêng biệt, mỗi phần tử cần một lần cập nhật điểm. Trong trường hợp xấu nhất, thao tác này có thể mất \(O(n\log n)\) thời gian.

Để xử lý hiệu quả các cập nhật trên đoạn, Segment Tree có thể được mở rộng bằng kỹ thuật Lazy Propagation.

## 6.2. Khái niệm Lazy Propagation

Lazy Propagation là kỹ thuật trì hoãn việc cập nhật các node con khi thông tin cập nhật có thể được lưu tạm tại node cha.

Thay vì đi xuống toàn bộ cây để thay đổi từng phần tử, thuật toán cập nhật trực tiếp thông tin tổng hợp của node đại diện cho một đoạn và lưu lại phần cập nhật đang chờ truyền xuống.

Khi một truy vấn hoặc cập nhật sau đó cần đi sâu vào node này, thông tin đang chờ mới được truyền xuống các node con.

Kỹ thuật này giảm số lượng node cần xử lý trong nhiều bài toán cập nhật trên đoạn.

## 6.3. Hai mảng thường sử dụng

Trong bài toán cộng một giá trị vào đoạn và truy vấn tổng, ta thường sử dụng:

- `tree[v]`: tổng hiện tại của đoạn do node \(v\) quản lý.
- `lazy[v]`: lượng giá trị cộng thêm đang chờ truyền xuống các node con.

Nếu node quản lý đoạn \([l,r]\) và nhận thao tác cộng \(d\), tổng của đoạn phải tăng thêm:

\[
d(r-l+1)
\]

Đồng thời, `lazy[v]` được tăng thêm \(d\), cho biết các node con vẫn cần nhận phần cập nhật tương ứng.

## 6.4. Hàm đẩy lazy xuống node con

Khi cần đi từ node cha xuống node con, thuật toán gọi `push` để truyền phần cập nhật đang chờ.

Với bài toán cộng \(d\) trên đoạn:
- Node con trái được cộng thêm \(d\) trên đoạn mà nó quản lý.
- Node con phải cũng được cộng thêm \(d\) trên đoạn mà nó quản lý.
- Giá trị lazy của hai node con được tăng thêm \(d\).
- Sau khi truyền, giá trị lazy của node cha được đặt về \(0\).

Nếu node cha quản lý đoạn \([l,r]\) và \(mid\) là điểm giữa, số phần tử của hai node con lần lượt là \(mid-l+1\) và \(r-mid\).

Vì vậy, tổng của mỗi node con phải được điều chỉnh theo đúng độ dài đoạn mà node đó quản lý.

## 6.5. Ba trường hợp trong cập nhật đoạn

Khi cần cộng \(d\) vào đoạn \([L,R]\), thuật toán xử lý như sau.

**Trường hợp 1: Không giao nhau.** Node nằm ngoài đoạn cập nhật nên không có thay đổi.

**Trường hợp 2: Nằm hoàn toàn trong đoạn cập nhật.** Cập nhật trực tiếp tổng của node theo độ dài đoạn và ghi nhận giá trị lazy cần truyền xuống.

**Trường hợp 3: Giao nhau một phần.** Đẩy lazy đang chờ xuống node con nếu cần, cập nhật đệ quy hai node con rồi tính lại tổng của node cha từ hai node con.

## 6.6. Pseudocode cập nhật đoạn

```text
APPLY(v, l, r, d):
    tree[v] = tree[v] + d * (r - l + 1)
    lazy[v] = lazy[v] + d

PUSH(v, l, r):
    IF lazy[v] == 0 OR l == r:
        RETURN

    mid = floor((l + r) / 2)

    APPLY(2*v, l, mid, lazy[v])
    APPLY(2*v+1, mid+1, r, lazy[v])

    lazy[v] = 0

RANGE_ADD(v, l, r, L, R, d):
    IF [l, r] does not intersect [L, R]:
        RETURN

    IF [l, r] is completely inside [L, R]:
        APPLY(v, l, r, d)
        RETURN

    PUSH(v, l, r)

    mid = floor((l + r) / 2)

    RANGE_ADD(2*v, l, mid, L, R, d)
    RANGE_ADD(2*v+1, mid+1, r, L, R, d)

    tree[v] = tree[2*v] + tree[2*v+1]
```

## 6.7. Truy vấn tổng khi có lazy

Khi truy vấn tổng trên đoạn, nếu node nằm hoàn toàn trong đoạn truy vấn, ta trả về tổng đang lưu.

Nếu chỉ giao một phần, cần đẩy lazy đang chờ xuống node con trước khi tiếp tục truy vấn sâu hơn. Sau đó, kết quả được tính bằng tổng của hai nhánh.

Một node không cần truyền lazy xuống con khi thuật toán có thể trả lời trực tiếp từ thông tin của chính node đó.

## 6.8. Ví dụ cập nhật đoạn

Với mảng:

\[
A=[2,1,5,3,4,7,6,8]
\]

Tổng ban đầu là \(36\).

Thực hiện thao tác cộng \(2\) vào đoạn \([2,5]\), các phần tử được thay đổi là:

\[
5\to7,\quad 3\to5,\quad
4\to6,\quad 7\to9
\]

Mảng mới là:

\[
A=[2,1,7,5,6,9,6,8]
\]

Tổng của đoạn \([2,5]\) tăng thêm:

\[
2\times4=8
\]

Tổng toàn bộ mảng tăng từ \(36\) lên \(44\).

Lazy Propagation cho phép xử lý cập nhật này bằng cách thay đổi những node đại diện cho các đoạn phù hợp, thay vì cập nhật riêng từng phần tử.

## 6.9. Độ phức tạp

Với Segment Tree sử dụng Lazy Propagation được thiết kế đúng:
- Xây dựng cây: \(O(n)\).
- Cập nhật cộng trên đoạn: \(O(\log n)\).
- Truy vấn tổng trên đoạn: \(O(\log n)\).
- Bộ nhớ: \(O(n)\).

Các giới hạn này áp dụng cho phép cập nhật cộng trên đoạn và truy vấn tổng với thao tác kết hợp hằng số thời gian.

---

# PHẦN VII. CÁC PHÉP KẾT HỢP VÀ BIẾN THỂ

## 7.1. Segment Tree truy vấn tổng

Mỗi node lưu tổng của các phần tử thuộc đoạn.

Phép kết hợp là cộng tổng của hai node con. Giá trị trung hòa của phép cộng là \(0\).

Cấu trúc này phù hợp với các bài toán tính tổng đoạn, kết hợp cập nhật điểm hoặc cập nhật đoạn bằng Lazy Propagation.

## 7.2. Segment Tree truy vấn minimum

Mỗi node lưu giá trị nhỏ nhất trong đoạn.

Phép kết hợp là:

\[
merge(x,y)=\min(x,y)
\]

Giá trị trung hòa phù hợp là \(+\infty\).

Với cập nhật điểm, thuật toán vẫn đi xuống lá rồi tính lại minimum của các node cha.

## 7.3. Segment Tree truy vấn maximum

Mỗi node lưu giá trị lớn nhất trong đoạn.

Phép kết hợp là:

\[
merge(x,y)=\max(x,y)
\]

Giá trị trung hòa phù hợp là \(-\infty\).

Cấu trúc này được sử dụng trong những bài toán cần tìm giá trị lớn nhất trên một khoảng.

## 7.4. Segment Tree lưu nhiều thông tin

Một node có thể lưu đồng thời nhiều thông tin tổng hợp, chẳng hạn tổng, minimum và maximum của một đoạn.

Khi đó, thao tác `merge` phải kết hợp tất cả các trường tương ứng từ hai node con.

Ví dụ, tổng của node cha bằng tổng hai node con, minimum của node cha bằng minimum của hai minimum con, còn maximum của node cha bằng maximum của hai maximum con.

Tuy nhiên, lưu nhiều thông tin hơn sẽ làm tăng bộ nhớ và chi phí xử lý tại mỗi node.

## 7.5. Điều kiện để phép kết hợp hoạt động đúng

Phép kết hợp cần bảo đảm rằng thông tin của một đoạn có thể được tính chính xác từ thông tin của các đoạn con.

Với nhiều loại Segment Tree cơ bản, phép kết hợp có tính kết hợp:

\[
merge(merge(a,b),c)
=
merge(a,merge(b,c))
\]

Điều kiện này giúp cấu trúc có thể kết hợp các đoạn theo những cách phân rã khác nhau mà vẫn bảo toàn kết quả.

Ngoài ra, cần xác định giá trị trung hòa phù hợp khi một đoạn không giao với truy vấn. Chọn sai giá trị trung hòa có thể làm sai kết quả của truy vấn.

## 7.6. Segment Tree lặp

Ngoài cách triển khai đệ quy, Segment Tree có thể được xây dựng theo cách lặp bằng mảng.

Trong một cách triển khai phổ biến, các node lá được đặt tại những vị trí liên tiếp ở nửa sau của mảng lưu cây. Các node cha được xây dựng từ dưới lên bằng cách kết hợp hai node con.

Truy vấn được thực hiện bằng cách di chuyển hai đầu mút của đoạn lên các tầng cha và kết hợp những node đại diện cho các đoạn cần thiết.

Segment Tree lặp có thể giảm chi phí gọi hàm đệ quy và thường được dùng trong các bài toán yêu cầu hiệu năng cao. Tuy nhiên, cách cài đặt và quy tắc đánh chỉ số khác với phiên bản đệ quy nên cần tránh trộn lẫn hai phương pháp.

## 7.7. Segment Tree động

Trong Segment Tree thông thường, ta thường cấp phát mảng với kích thước tỷ lệ thuận với \(n\).

Nếu miền chỉ số rất lớn nhưng số vị trí thực sự được sử dụng ít, việc cấp phát toàn bộ cây có thể không khả thi.

Segment Tree động chỉ tạo node khi cần truy cập hoặc cập nhật một phần miền chỉ số. Cách này phù hợp với miền giá trị lớn, chẳng hạn chỉ số đến \(10^9\), nhưng chỉ có một số lượng nhỏ các vị trí được cập nhật.

Chi phí bộ nhớ khi đó phụ thuộc vào số node thực tế được tạo ra, thay vì luôn phải cấp phát cho toàn bộ cây.

---

# PHẦN VIII. SO SÁNH VỚI CÁC CẤU TRÚC DỮ LIỆU KHÁC

## 8.1. Mảng thông thường

Mảng thông thường có thể đọc hoặc cập nhật một phần tử trong \(O(1)\).

Tuy nhiên, truy vấn tổng trên đoạn thường mất \(O(n)\) trong trường hợp xấu nhất nếu phải duyệt các phần tử thuộc đoạn.

Mảng phù hợp với những bài toán có ít truy vấn hoặc dữ liệu không cần các thao tác tổng hợp phức tạp.

## 8.2. Prefix Sum

Prefix Sum lưu tổng tiền tố của mảng để trả lời truy vấn tổng đoạn trong \(O(1)\).

Nếu \(P[i]\) là tổng các phần tử từ đầu mảng đến vị trí \(i\), tổng đoạn \([L,R]\) có thể được tính bằng hiệu hai tổng tiền tố thích hợp.

Tuy nhiên, khi một phần tử thay đổi, nhiều tổng tiền tố phía sau vị trí đó có thể phải cập nhật lại. Do đó, Prefix Sum phù hợp hơn với dữ liệu tĩnh, ít hoặc không có cập nhật.

## 8.3. Fenwick Tree

Fenwick Tree, còn gọi là Binary Indexed Tree, là cấu trúc dữ liệu hỗ trợ các thao tác như cập nhật điểm và truy vấn tổng tiền tố trong \(O(\log n)\).

Với cập nhật điểm và truy vấn tổng đoạn, Fenwick Tree thường có cách cài đặt gọn và bộ nhớ thấp hơn Segment Tree.

Tuy nhiên, Segment Tree linh hoạt hơn khi cần lưu các thông tin tổng hợp phức tạp, thực hiện truy vấn minimum/maximum với các điều kiện phù hợp hoặc mở rộng sang các thao tác cập nhật đoạn.

## 8.4. Sparse Table

Sparse Table phù hợp với các truy vấn trên mảng tĩnh, đặc biệt là minimum và maximum trên đoạn.

Sau khi tiền xử lý \(O(n\log n)\), một số loại truy vấn như RMQ có thể được trả lời trong \(O(1)\).

Nhược điểm là Sparse Table thông thường không phù hợp với cập nhật dữ liệu tùy ý sau khi xây dựng.

## 8.5. Bảng so sánh

| Cấu trúc | Truy vấn tổng đoạn | Cập nhật điểm | Phù hợp dữ liệu động |
|---|---:|---:|---|
| Mảng thường | \(O(n)\) | \(O(1)\) | Có, nhưng truy vấn đoạn chậm |
| Prefix Sum | \(O(1)\) | \(O(n)\) | Không tối ưu |
| Fenwick Tree | \(O(\log n)\) | \(O(\log n)\) | Có |
| Segment Tree | \(O(\log n)\) | \(O(\log n)\) | Có |
| Sparse Table | Không phải lựa chọn chính cho tổng đoạn động | Không tối ưu | Không |

Các độ phức tạp trên là trường hợp điển hình cho những cách triển khai tương ứng; chúng có thể thay đổi tùy loại phép toán và biến thể của cấu trúc.

---

# PHẦN IX. ỨNG DỤNG VÀ BÀI TOÁN THỰC TẾ

## 9.1. Quản lý doanh thu theo ngày

Một hệ thống có thể lưu doanh thu mỗi ngày trong một mảng.

Segment Tree có thể trả lời tổng doanh thu trong một khoảng ngày, cập nhật doanh thu khi dữ liệu được điều chỉnh và tìm ngày có doanh thu lớn nhất hoặc nhỏ nhất trong một giai đoạn.

Nếu dữ liệu được cập nhật thường xuyên, Segment Tree giúp tránh tính lại toàn bộ khoảng ngày sau mỗi thay đổi.

## 9.2. Phân tích điểm số

Trong một hệ thống quản lý điểm, mỗi phần tử của mảng có thể đại diện cho điểm số của một sinh viên hoặc kết quả của một lượt thi.

Segment Tree có thể tính tổng điểm trên một nhóm vị trí, tìm điểm cao nhất hoặc thấp nhất và cập nhật kết quả khi có điểm mới.

Tuy nhiên, việc lựa chọn cấu trúc dữ liệu phải dựa trên dạng truy vấn thực tế và cách dữ liệu được cập nhật.

## 9.3. Xử lý truy vấn trong lập trình thi đấu

Nhiều bài toán cho một mảng ban đầu và một chuỗi thao tác. Mỗi thao tác có thể là cập nhật một phần tử, truy vấn tổng đoạn hoặc tìm minimum/maximum.

Segment Tree đặc biệt phù hợp khi số lượng thao tác lớn và cần xử lý trực tuyến, nghĩa là kết quả của thao tác trước có thể ảnh hưởng đến trạng thái được sử dụng ở thao tác tiếp theo.

## 9.4. Đếm tần suất và tìm phần tử thứ k

Segment Tree có thể lưu số lượng phần tử trong các miền giá trị hoặc tần suất tại từng vị trí.

Nếu mỗi node lưu tổng tần suất của đoạn, có thể tìm vị trí của phần tử thứ \(k\) bằng cách so sánh \(k\) với tổng tần suất của nhánh trái, sau đó quyết định tiếp tục đi xuống nhánh trái hay nhánh phải.

Ứng dụng này đòi hỏi thông tin lưu tại node và điều kiện truy vấn phải được thiết kế phù hợp với bài toán.

## 9.5. Quản lý khoảng và các sự kiện

Trong những bài toán quản lý sự kiện theo thời gian, mỗi vị trí có thể đại diện cho một mốc thời gian hoặc một tọa độ đã được nén.

Segment Tree có thể hỗ trợ truy vấn tổng hợp trên một khoảng và cập nhật trạng thái của các khoảng liên quan.

Đối với miền tọa độ lớn, có thể sử dụng nén tọa độ hoặc Segment Tree động để giảm lượng bộ nhớ cần thiết.

---

# PHẦN X. LỖI THƯỜNG GẶP VÀ CÁCH KIỂM THỬ

## 10.1. Sai chỉ số

Một lỗi phổ biến là trộn lẫn chỉ số bắt đầu từ \(0\) với chỉ số bắt đầu từ \(1\).

Nếu mảng sử dụng chỉ số từ \(0\) đến \(n-1\), mọi đoạn truy vấn và điều kiện cập nhật phải tuân theo quy ước này.

Ngoài ra, đoạn \([L,R]\) thường là đoạn đóng, nghĩa là bao gồm cả hai đầu mút. Khi tính độ dài đoạn, phải sử dụng \(R-L+1\).

## 10.2. Sai điều kiện giao nhau

Khi kiểm tra đoạn node \([l,r]\) có giao với đoạn truy vấn \([L,R]\) hay không, hai đoạn không giao nhau nếu:

\[
r<L\quad\text{hoặc}\quad R<l
\]

Nếu một trong hai điều kiện trên đúng, node không đóng góp vào kết quả.

Ngược lại, nếu \(L\le l\) và \(r\le R\), đoạn node nằm hoàn toàn trong đoạn truy vấn.

Việc xác định sai các điều kiện này có thể dẫn đến bỏ sót phần tử hoặc tính một phần tử nhiều lần.

## 10.3. Không cập nhật lại node cha

Sau khi cập nhật node lá, các node cha phải được tính toán lại từ hai node con.

Nếu quên bước này, thông tin tổng hợp tại các node phía trên sẽ không còn phản ánh đúng dữ liệu hiện tại.

## 10.4. Đẩy lazy sai thời điểm

Khi sử dụng Lazy Propagation, một node có thể lưu thông tin cập nhật đang chờ truyền xuống.

Nếu truy vấn đi sâu vào node con mà không truyền phần cập nhật cần thiết, kết quả có thể bị cũ.

Ngược lại, nếu xử lý lazy không nhất quán, thuật toán có thể áp dụng một cập nhật nhiều lần hoặc làm mất cập nhật trước đó.

Do đó, cần xác định rõ khi nào áp dụng lazy, khi nào truyền xuống và khi nào tính lại node cha.

## 10.5. Tràn số nguyên

Nếu mảng có phần tử lớn và số lượng phần tử nhiều, tổng trên một đoạn có thể vượt giới hạn của kiểu số nguyên 32 bit.

Ví dụ, \(10^5\) phần tử đều có giá trị \(10^9\) tạo ra tổng lên đến \(10^{14}\).

Trong C++, cần sử dụng kiểu `long long` cho những giá trị có thể vượt giới hạn của `int`.

## 10.6. Kiểm thử bằng vét cạn

Một cách hiệu quả để phát hiện lỗi là xây dựng một chương trình kiểm tra đơn giản bằng mảng thường.

Với mỗi thao tác ngẫu nhiên:
1. Thực hiện thao tác trên Segment Tree.
2. Thực hiện cùng thao tác trên mảng thường.
3. So sánh kết quả truy vấn của hai cách.
4. Nếu có sai khác, lưu lại dữ liệu đầu vào và chuỗi thao tác gây lỗi.

Cách kiểm thử này đặc biệt hữu ích với Lazy Propagation vì lỗi có thể chỉ xuất hiện sau nhiều thao tác cập nhật và truy vấn liên tiếp.

## 10.7. Các trường hợp biên

Cần kiểm thử ít nhất những trường hợp sau:
- Mảng chỉ có một phần tử.
- Truy vấn đúng một phần tử.
- Truy vấn toàn bộ mảng.
- Cập nhật phần tử đầu tiên hoặc cuối cùng.
- Cập nhật một đoạn bao phủ toàn bộ mảng.
- Cập nhật một đoạn không chứa node gốc nhưng nằm hoàn toàn trong một nhánh.
- Nhiều lần cập nhật chồng lấn.
- Truy vấn ngay sau một cập nhật đoạn.
- Mảng chứa số âm.
- Giá trị tổng lớn có khả năng gây tràn số.

---

# PHẦN XI. ĐỊNH HƯỚNG TRIỂN KHAI TRONG C++

## 11.1. Các thành phần chính

Một chương trình Segment Tree cơ bản có thể được chia thành những thành phần:
- Mảng đầu vào `a`.
- Mảng lưu thông tin node `tree`.
- Hàm `build()` để xây dựng cây.
- Hàm `query()` để truy vấn trên đoạn.
- Hàm `update()` để cập nhật một phần tử.
- Hàm `merge()` hoặc logic tương đương để kết hợp hai node con.

Với phiên bản Lazy Propagation, cần bổ sung mảng `lazy` và các hàm để áp dụng, truyền và xử lý cập nhật đang chờ.

## 11.2. Lựa chọn giao diện hàm

Nên thiết kế giao diện hàm nhất quán để tránh truyền nhầm các đoạn.

Ví dụ, có thể quy ước mọi hàm đều nhận:
- Chỉ số node \(v\).
- Đoạn mà node quản lý \([l,r]\).
- Tham số truy vấn hoặc cập nhật cần thiết.

Nếu toàn bộ chương trình sử dụng chỉ số mảng từ \(0\), các hàm nên thống nhất sử dụng đoạn đóng \([L,R]\).

## 11.3. Phân chia module

Trong một dự án lớn hơn, có thể tách riêng:
- Module xây dựng cây.
- Module truy vấn.
- Module cập nhật điểm.
- Module Lazy Propagation.
- Module kiểm thử và so sánh kết quả.

Cách phân chia này giúp xác định lỗi dễ hơn, đồng thời cho phép mở rộng cấu trúc dữ liệu mà không cần viết lại toàn bộ chương trình.

## 11.4. Tiêu chí đánh giá

Khi đánh giá một triển khai Segment Tree, cần kiểm tra:
- Tính chính xác của kết quả truy vấn.
- Tính chính xác sau các cập nhật liên tiếp.
- Độ phức tạp thời gian phù hợp với yêu cầu bài toán.
- Bộ nhớ sử dụng.
- Khả năng xử lý các trường hợp biên.
- Tính rõ ràng và nhất quán của code.

---

# PHẦN XII. TỔNG KẾT VÀ CÂU HỎI THẢO LUẬN

## 12.1. Những kiến thức cốt lõi

Segment Tree là cấu trúc dữ liệu cho phép lưu thông tin tổng hợp của nhiều đoạn trong một mảng.

Các node được tổ chức theo cấu trúc phân đoạn nhị phân. Node lá lưu thông tin của một phần tử, còn node cha lưu thông tin được kết hợp từ hai node con.

Đối với các phép kết hợp phù hợp, Segment Tree hỗ trợ xây dựng trong \(O(n)\), truy vấn đoạn trong \(O(\log n)\) và cập nhật điểm trong \(O(\log n)\).

Lazy Propagation mở rộng Segment Tree để xử lý hiệu quả nhiều loại cập nhật trên đoạn bằng cách trì hoãn việc truyền cập nhật xuống các node con.

Việc lựa chọn Segment Tree cần dựa trên yêu cầu truy vấn, kiểu cập nhật, kích thước dữ liệu và các cấu trúc dữ liệu thay thế.

## 12.2. Câu hỏi kiểm tra kiến thức

1. Vì sao truy vấn tổng trên một đoạn bằng mảng thông thường có thể mất \(O(n)\)?
2. Mỗi node trong Segment Tree đại diện cho thông tin gì?
3. Vì sao chiều cao Segment Tree là \(O(\log n)\)?
4. Vì sao xây dựng Segment Tree có độ phức tạp \(O(n)\)?
5. Truy vấn một đoạn được xử lý như thế nào khi node nằm ngoài, nằm trong hoàn toàn hoặc chỉ giao một phần với đoạn truy vấn?
6. Sau khi cập nhật một phần tử, vì sao phải tính lại các node cha?
7. Lazy Propagation giải quyết hạn chế nào của cập nhật từng phần tử?
8. Với thao tác cộng \(d\) vào một đoạn có \(k\) phần tử, tổng của đoạn tăng bao nhiêu?
9. Vì sao không phải lúc nào cũng cần truyền lazy xuống node con ngay lập tức?
10. Khi nào Prefix Sum hoặc Fenwick Tree là lựa chọn phù hợp hơn Segment Tree?
11. Những lỗi nào có thể xuất hiện khi sử dụng chỉ số \(0\) và chỉ số \(1\) không nhất quán?
12. Làm thế nào kiểm tra tính đúng đắn của Segment Tree bằng một mảng thông thường?

## 12.3. Bài tập thực hành

**Bài 1 — Truy vấn tổng:** Cho mảng \(A\) gồm \(n\) số nguyên. Xây dựng Segment Tree để trả lời \(q\) truy vấn tổng trên đoạn \([L,R]\).

**Bài 2 — Cập nhật điểm:** Mở rộng bài 1 bằng thao tác gán giá trị mới cho một phần tử tại vị trí \(p\).

**Bài 3 — Truy vấn minimum:** Thay đổi thông tin lưu ở mỗi node để tìm giá trị nhỏ nhất trong đoạn.

**Bài 4 — Lazy Propagation:** Hỗ trợ hai thao tác: cộng một số nguyên \(d\) vào mọi phần tử trong đoạn \([L,R]\), và truy vấn tổng của đoạn \([L,R]\).

**Bài 5 — Kiểm thử ngẫu nhiên:** Sinh các mảng và thao tác ngẫu nhiên, sau đó so sánh kết quả Segment Tree với cách xử lý trực tiếp trên mảng.

**Bài 6 — Tìm phần tử thứ \(k\):** Xây dựng Segment Tree lưu tần suất và tìm vị trí của phần tử thứ \(k\) trong một dãy có các tần suất không âm.

## 12.4. Kết luận

Segment Tree là một công cụ quan trọng trong lập trình thuật toán vì cho phép tổ chức thông tin theo các đoạn và trả lời truy vấn hiệu quả trong khi dữ liệu thay đổi.

Để sử dụng đúng cấu trúc dữ liệu này, người lập trình cần hiểu cách phân rã đoạn, cách kết hợp thông tin ở node cha, các trường hợp của truy vấn, cơ chế cập nhật điểm và nguyên lý trì hoãn cập nhật của Lazy Propagation.

Quan trọng hơn, việc lựa chọn cấu trúc dữ liệu không chỉ dựa trên tốc độ mà còn phải dựa vào loại thao tác cần hỗ trợ. Hiểu rõ ưu điểm, hạn chế và độ phức tạp của Segment Tree sẽ giúp giải quyết nhiều bài toán thực tế và bài toán lập trình thi đấu một cách hiệu quả.
