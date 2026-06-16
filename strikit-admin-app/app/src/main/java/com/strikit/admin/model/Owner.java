package com.strikit.admin.model;

import com.google.gson.annotations.SerializedName;

public class Owner {
    private int id;
    private String name;
    private String mobile;
    private String turfName;
    private String location;
    private String photoUrls;
    private String gst;
    private String msme;
    private String msmeCardUrl;
    private String utilityBillUrl;
    private boolean verified;
    private String businessPhone;
    private boolean subscriptionActive;
    private String subscriptionExpiry;
    private String createdAt;

    // Getters and Setters
    public int getId() { return id; }
    public void setId(int id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getMobile() { return mobile; }
    public void setMobile(String mobile) { this.mobile = mobile; }

    public String getTurfName() { return turfName; }
    public void setTurfName(String turfName) { this.turfName = turfName; }

    public String getLocation() { return location; }
    public void setLocation(String location) { this.location = location; }

    public String getPhotoUrls() { return photoUrls; }
    public void setPhotoUrls(String photoUrls) { this.photoUrls = photoUrls; }

    public String getGst() { return gst; }
    public void setGst(String gst) { this.gst = gst; }

    public String getMsme() { return msme; }
    public void setMsme(String msme) { this.msme = msme; }

    public String getMsmeCardUrl() { return msmeCardUrl; }
    public void setMsmeCardUrl(String msmeCardUrl) { this.msmeCardUrl = msmeCardUrl; }

    public String getUtilityBillUrl() { return utilityBillUrl; }
    public void setUtilityBillUrl(String utilityBillUrl) { this.utilityBillUrl = utilityBillUrl; }

    public boolean isVerified() { return verified; }
    public void setVerified(boolean verified) { this.verified = verified; }

    public String getBusinessPhone() { return businessPhone; }
    public void setBusinessPhone(String businessPhone) { this.businessPhone = businessPhone; }

    public boolean isSubscriptionActive() { return subscriptionActive; }
    public void setSubscriptionActive(boolean subscriptionActive) { this.subscriptionActive = subscriptionActive; }

    public String getSubscriptionExpiry() { return subscriptionExpiry; }
    public void setSubscriptionExpiry(String subscriptionExpiry) { this.subscriptionExpiry = subscriptionExpiry; }

    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String createdAt) { this.createdAt = createdAt; }
}
