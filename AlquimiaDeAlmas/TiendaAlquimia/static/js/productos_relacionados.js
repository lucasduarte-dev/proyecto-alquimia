document.addEventListener('DOMContentLoaded', function () {
  console.log("Archivo JS cargado correctamente");
  const track = document.getElementById('carruselTrack');
  const slides = track.querySelectorAll('.carrusel-slide');
  const prevBtn = document.getElementById('prevBtn');
  const nextBtn = document.getElementById('nextBtn');
  const indicadoresContainer = document.getElementById('indicadores');

  let slideWidth = slides[0].getBoundingClientRect().width;
  let currentIndex = 0;
  let slidesPerView = getSlidesPerView();
  let totalGroups = Math.ceil(slides.length / slidesPerView);
  let autoplayInterval;

  for (let i = 0; i < totalGroups; i++) {
    const indicador = document.createElement('div');
    indicador.classList.add('indicador');
    if (i === 0) indicador.classList.add('active');
    indicador.addEventListener('click', () => goToSlide(i));
    indicadoresContainer.appendChild(indicador);
  }

  startAutoplay();

  window.addEventListener('resize', () => {
    slideWidth = slides[0].getBoundingClientRect().width;
    slidesPerView = getSlidesPerView();
    totalGroups = Math.ceil(slides.length / slidesPerView);
    updateSlidePosition();
    updateIndicadores();
  });

  prevBtn.addEventListener('click', () => {
    stopAutoplay();
    prevSlide();
    startAutoplay();
  });

  nextBtn.addEventListener('click', () => {
    stopAutoplay();
    nextSlide();
    startAutoplay();
  });

  track.addEventListener('mouseenter', stopAutoplay);
  track.addEventListener('mouseleave', startAutoplay);

  function getSlidesPerView() {
    if (window.innerWidth < 576) return 1;
    if (window.innerWidth < 992) return 2;
    return 3;
  }

  function updateSlidePosition() {
    // Este es el cambio clave: usar currentIndex * slideWidth, tal como en el código original
    track.style.transform = `translateX(-${currentIndex * slideWidth}px)`;
    track.style.transition = 'transform 0.5s ease-in-out';
    const slidesToShow = Array.from(slides).slice(currentIndex * slidesPerView, (currentIndex + 1) * slidesPerView);
  }

  function updateIndicadores() {
    const indicadores = indicadoresContainer.querySelectorAll('.indicador');
    indicadores.forEach((indicador, index) => {
      indicador.classList.toggle('active', index === currentIndex);
    });
  }

  function goToSlide(index) {
    currentIndex = index;
    if (currentIndex >= totalGroups) currentIndex = 0;
    if (currentIndex < 0) currentIndex = totalGroups - 1;
    updateSlidePosition();
    updateIndicadores();
  }

  function nextSlide() {
    goToSlide(currentIndex + 1);
  }

  function prevSlide() {
    goToSlide(currentIndex - 1);
  }

  function startAutoplay() {
    stopAutoplay();
    autoplayInterval = setInterval(nextSlide, 7000);
  }

  function stopAutoplay() {
    clearInterval(autoplayInterval);
  }
});