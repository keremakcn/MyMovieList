document.addEventListener("DOMContentLoaded", function () {
    // --- Custom confirmation modal -------------------------------
    // Replaces the native browser confirm() (which can't be styled)
    // for any form with a data-confirm="..." attribute, e.g.
    // <form data-confirm="Delete this movie?">.
    const modal = document.getElementById("confirm-modal");

    if (!modal) {
        return;
    }

    const modalMessage = modal.querySelector(".confirm-modal-message");
    const confirmBtn = modal.querySelector(".confirm-modal-confirm");
    const cancelBtn = modal.querySelector(".confirm-modal-cancel");
    let pendingForm = null;

    function openModal(form) {
        pendingForm = form;
        modalMessage.textContent = form.dataset.confirm || "Are you sure?";
        modal.classList.add("open");
    }

    function closeModal() {
        pendingForm = null;
        modal.classList.remove("open");
    }

    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            openModal(form);
        });
    });

    confirmBtn.addEventListener("click", function () {
        if (pendingForm) {
            pendingForm.submit();
        }
        closeModal();
    });

    cancelBtn.addEventListener("click", closeModal);

    modal.addEventListener("click", function (event) {
        if (event.target === modal) {
            closeModal();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && modal.classList.contains("open")) {
            closeModal();
        }
    });
});