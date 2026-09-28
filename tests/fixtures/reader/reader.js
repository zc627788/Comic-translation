const changingImage = document.getElementById('changing-image');
let secondPage = false;
document.getElementById('swap-source').addEventListener('click', () => {
  secondPage = !secondPage;
  changingImage.src = secondPage ? '/assets/page-two.svg' : '/assets/page-one.svg';
  document.getElementById('swap-status').textContent = `当前显示：${secondPage ? '第二张' : '第一张'}`;
});

let appendedCount = 0;
document.getElementById('append-image').addEventListener('click', () => {
  if (appendedCount >= 10) return;
  const image = document.createElement('img');
  image.src = '/assets/page-two.svg';
  image.alt = `追加测试图片 ${++appendedCount}`;
  image.width = 720;
  image.height = 960;
  image.className = 'page compact';
  document.getElementById('appended-images').append(image);
  document.getElementById('append-status').textContent = `已追加 ${appendedCount} 张`;
  if (appendedCount === 10) document.getElementById('append-image').disabled = true;
});
