package com.strikit.admin.model;

public class Payout {
    private int id;
    private int bookingId;
    private int ownerId;
    private String ownerName;
    private String turfName;
    private String razorpayPaymentId;
    private String razorpayPayoutId;
    private String totalPaid;
    private String ownerShare;
    private String platformFee;
    private String ownerUpiId;
    private String status;
    private String idempotencyKey;
    private int attemptCount;
    private String failureReason;
    private String createdAt;
    private String updatedAt;

    // Getters and Setters
    public int getId() { return id; }
    public void setId(int id) { this.id = id; }

    public int getBookingId() { return bookingId; }
    public void setBookingId(int bookingId) { this.bookingId = bookingId; }

    public int getOwnerId() { return ownerId; }
    public void setOwnerId(int ownerId) { this.ownerId = ownerId; }

    public String getOwnerName() { return ownerName; }
    public void setOwnerName(String ownerName) { this.ownerName = ownerName; }

    public String getTurfName() { return turfName; }
    public void setTurfName(String turfName) { this.turfName = turfName; }

    public String getRazorpayPaymentId() { return razorpayPaymentId; }
    public void setRazorpayPaymentId(String razorpayPaymentId) { this.razorpayPaymentId = razorpayPaymentId; }

    public String getRazorpayPayoutId() { return razorpayPayoutId; }
    public void setRazorpayPayoutId(String razorpayPayoutId) { this.razorpayPayoutId = razorpayPayoutId; }

    public String getTotalPaid() { return totalPaid; }
    public void setTotalPaid(String totalPaid) { this.totalPaid = totalPaid; }

    public String getOwnerShare() { return ownerShare; }
    public void setOwnerShare(String ownerShare) { this.ownerShare = ownerShare; }

    public String getPlatformFee() { return platformFee; }
    public void setPlatformFee(String platformFee) { this.platformFee = platformFee; }

    public String getOwnerUpiId() { return ownerUpiId; }
    public void setOwnerUpiId(String ownerUpiId) { this.ownerUpiId = ownerUpiId; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public String getIdempotencyKey() { return idempotencyKey; }
    public void setIdempotencyKey(String idempotencyKey) { this.idempotencyKey = idempotencyKey; }

    public int getAttemptCount() { return attemptCount; }
    public void setAttemptCount(int attemptCount) { this.attemptCount = attemptCount; }

    public String getFailureReason() { return failureReason; }
    public void setFailureReason(String failureReason) { this.failureReason = failureReason; }

    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String createdAt) { this.createdAt = createdAt; }

    public String getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(String updatedAt) { this.updatedAt = updatedAt; }
}
