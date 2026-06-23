package com.strikit.admin.model;

public class AdminStats {
    private int activeTurfs;
    private int pendingVerifications;
    private int failedPayouts;
    private int totalBookings;
    private long totalRevenuePaise;
    private int pendingRefundRequests;

    public int getActiveTurfs() { return activeTurfs; }
    public void setActiveTurfs(int activeTurfs) { this.activeTurfs = activeTurfs; }

    public int getPendingVerifications() { return pendingVerifications; }
    public void setPendingVerifications(int pendingVerifications) { this.pendingVerifications = pendingVerifications; }

    public int getFailedPayouts() { return failedPayouts; }
    public void setFailedPayouts(int failedPayouts) { this.failedPayouts = failedPayouts; }

    public int getTotalBookings() { return totalBookings; }
    public void setTotalBookings(int totalBookings) { this.totalBookings = totalBookings; }

    public long getTotalRevenuePaise() { return totalRevenuePaise; }
    public void setTotalRevenuePaise(long totalRevenuePaise) { this.totalRevenuePaise = totalRevenuePaise; }

    public int getPendingRefundRequests() { return pendingRefundRequests; }
    public void setPendingRefundRequests(int pendingRefundRequests) { this.pendingRefundRequests = pendingRefundRequests; }
}
