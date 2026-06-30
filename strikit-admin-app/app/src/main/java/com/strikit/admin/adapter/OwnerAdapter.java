package com.strikit.admin.adapter;

import android.content.Context;
import android.content.res.ColorStateList;
import android.text.Html;
import android.text.method.LinkMovementMethod;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;
import androidx.annotation.NonNull;
import androidx.core.content.ContextCompat;
import androidx.recyclerview.widget.RecyclerView;
import com.strikit.admin.R;
import com.strikit.admin.model.Owner;
import java.util.ArrayList;
import java.util.List;

public class OwnerAdapter extends RecyclerView.Adapter<OwnerAdapter.OwnerViewHolder> {

    public interface OnOwnerActionListener {
        void onApprove(Owner owner);
        void onReject(Owner owner);
        void onDelete(Owner owner);
        void onLinkRoute(Owner owner);
    }

    private List<Owner> ownersList = new ArrayList<>();
    private final OnOwnerActionListener listener;
    private final Context context;

    public OwnerAdapter(Context context, OnOwnerActionListener listener) {
        this.context = context;
        this.listener = listener;
    }

    public void setOwners(List<Owner> owners) {
        this.ownersList = owners != null ? owners : new ArrayList<>();
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public OwnerViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_owner, parent, false);
        return new OwnerViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull OwnerViewHolder holder, int position) {
        Owner owner = ownersList.get(position);
        
        holder.tvTurfName.setText(owner.getTurfName());
        holder.tvOwnerId.setText("ID: #" + owner.getId());
        holder.tvOwnerName.setText("Owner: " + owner.getName());
        holder.tvOwnerMobile.setText("Register Phone: +" + owner.getMobile());

        if (owner.getBusinessPhone() != null && !owner.getBusinessPhone().isEmpty()) {
            holder.tvBusinessPhone.setText("Business Bot Phone: +" + owner.getBusinessPhone());
            holder.tvBusinessPhone.setVisibility(View.VISIBLE);
        } else {
            holder.tvBusinessPhone.setText("Business Bot Phone: Not Connected");
            holder.tvBusinessPhone.setVisibility(View.VISIBLE);
        }

        if (owner.getLocation() != null && !owner.getLocation().isEmpty()) {
            String mapsUrl = owner.getLocation();
            if (mapsUrl.startsWith("location:")) {
                String coords = mapsUrl.replace("location:", "").trim();
                mapsUrl = "https://www.google.com/maps/search/?api=1&query=" + coords;
            } else if (!mapsUrl.startsWith("http://") && !mapsUrl.startsWith("https://")) {
                mapsUrl = "https://www.google.com/maps/search/?api=1&query=" + android.net.Uri.encode(mapsUrl);
            }
            String linkText = "<a href=\"" + mapsUrl + "\">View on Google Maps</a>";
            holder.tvLocation.setText(Html.fromHtml("Location: " + linkText, Html.FROM_HTML_MODE_COMPACT));
            holder.tvLocation.setMovementMethod(LinkMovementMethod.getInstance());
            holder.tvLocation.setVisibility(View.VISIBLE);
        } else {
            holder.tvLocation.setVisibility(View.GONE);
        }

        // Bind MSME Certificate
        if (owner.getMsmeCardUrl() != null && !owner.getMsmeCardUrl().isEmpty()) {
            String linkText = "<a href=\"" + owner.getMsmeCardUrl() + "\">View Certificate</a>";
            holder.tvMsme.setText(Html.fromHtml("MSME: " + linkText, Html.FROM_HTML_MODE_COMPACT));
            holder.tvMsme.setMovementMethod(LinkMovementMethod.getInstance());
            holder.tvMsme.setVisibility(View.VISIBLE);
        } else if (owner.getMsme() != null && !owner.getMsme().isEmpty()) {
            holder.tvMsme.setText("MSME: " + owner.getMsme());
            holder.tvMsme.setMovementMethod(null);
            holder.tvMsme.setVisibility(View.VISIBLE);
        } else {
            holder.tvMsme.setVisibility(View.GONE);
        }

        // Bind Utility Bill
        if (owner.getUtilityBillUrl() != null && !owner.getUtilityBillUrl().isEmpty()) {
            String linkText = "<a href=\"" + owner.getUtilityBillUrl() + "\">View Bill</a>";
            holder.tvUtilityBill.setText(Html.fromHtml("Utility Bill: " + linkText, Html.FROM_HTML_MODE_COMPACT));
            holder.tvUtilityBill.setMovementMethod(LinkMovementMethod.getInstance());
            holder.tvUtilityBill.setVisibility(View.VISIBLE);
        } else {
            holder.tvUtilityBill.setVisibility(View.GONE);
        }

        // Bind Turf Photos
        if (owner.getPhotoUrls() != null && !owner.getPhotoUrls().isEmpty()) {
            try {
                com.google.gson.JsonArray array = new com.google.gson.JsonParser().parse(owner.getPhotoUrls()).getAsJsonArray();
                if (array.size() > 0) {
                    StringBuilder sb = new StringBuilder("Turf Photos: ");
                    for (int i = 0; i < array.size(); i++) {
                        String url = array.get(i).getAsString();
                        if (i > 0) {
                            sb.append(" | ");
                        }
                        sb.append("<a href=\"").append(url).append("\">Photo ").append(i + 1).append("</a>");
                    }
                    holder.tvPhotos.setText(Html.fromHtml(sb.toString(), Html.FROM_HTML_MODE_COMPACT));
                    holder.tvPhotos.setMovementMethod(LinkMovementMethod.getInstance());
                    holder.tvPhotos.setVisibility(View.VISIBLE);
                } else {
                    holder.tvPhotos.setVisibility(View.GONE);
                }
            } catch (Exception e) {
                String url = owner.getPhotoUrls();
                if (url.startsWith("http")) {
                    String linkText = "<a href=\"" + url + "\">View Photo</a>";
                    holder.tvPhotos.setText(Html.fromHtml("Turf Photos: " + linkText, Html.FROM_HTML_MODE_COMPACT));
                    holder.tvPhotos.setMovementMethod(LinkMovementMethod.getInstance());
                    holder.tvPhotos.setVisibility(View.VISIBLE);
                } else {
                    holder.tvPhotos.setVisibility(View.GONE);
                }
            }
        } else {
            holder.tvPhotos.setVisibility(View.GONE);
        }

        // Verification Badge Styling
        if (owner.isVerified()) {
            holder.badgeVerified.setText("VERIFIED");
            holder.badgeVerified.setTextColor(ContextCompat.getColor(context, R.color.bg_dark));
            holder.badgeVerified.setBackgroundTintList(ColorStateList.valueOf(ContextCompat.getColor(context, R.color.status_verified)));
            
            holder.btnApprove.setVisibility(View.GONE);
            holder.btnReject.setVisibility(View.VISIBLE);
        } else {
            holder.badgeVerified.setText("PENDING VERIFICATION");
            holder.badgeVerified.setTextColor(ContextCompat.getColor(context, R.color.bg_dark));
            holder.badgeVerified.setBackgroundTintList(ColorStateList.valueOf(ContextCompat.getColor(context, R.color.status_pending)));
            
            holder.btnApprove.setVisibility(View.VISIBLE);
            holder.btnReject.setVisibility(View.GONE);
        }

        // Subscription Status Badge Styling
        if (owner.isSubscriptionActive()) {
            holder.badgeSubscription.setText("TRIAL / ACTIVE");
            holder.badgeSubscription.setTextColor(ContextCompat.getColor(context, R.color.bg_dark));
            holder.badgeSubscription.setBackgroundTintList(ColorStateList.valueOf(ContextCompat.getColor(context, R.color.status_active)));

            if (owner.getSubscriptionExpiry() != null && !owner.getSubscriptionExpiry().isEmpty()) {
                // Formatting date string: e.g. "2026-06-08T20:20:58.000Z" -> "Expires: 2026-06-08"
                String expiryStr = owner.getSubscriptionExpiry();
                if (expiryStr.contains("T")) {
                    expiryStr = expiryStr.split("T")[0];
                }
                holder.tvExpiryDate.setText("Trial Expiry: " + expiryStr);
                holder.tvExpiryDate.setVisibility(View.VISIBLE);
            } else {
                holder.tvExpiryDate.setVisibility(View.GONE);
            }
        } else {
            holder.badgeSubscription.setText("INACTIVE / EXPIRED");
            holder.badgeSubscription.setTextColor(ContextCompat.getColor(context, R.color.bg_dark));
            holder.badgeSubscription.setBackgroundTintList(ColorStateList.valueOf(ContextCompat.getColor(context, R.color.status_inactive)));
            holder.tvExpiryDate.setVisibility(View.GONE);
        }

        // Bind Route Account info
        if (owner.getRazorpayContactId() != null && !owner.getRazorpayContactId().trim().isEmpty()) {
            holder.tvRouteAccount.setText("Route Account: " + owner.getRazorpayContactId());
            holder.btnLinkRoute.setText("Edit ID");
        } else {
            holder.tvRouteAccount.setText("Route Account: Not configured");
            holder.btnLinkRoute.setText("Link ID");
        }

        // Wire Button Click Handlers
        holder.btnLinkRoute.setOnClickListener(v -> {
            if (listener != null) {
                listener.onLinkRoute(owner);
            }
        });
        holder.btnApprove.setOnClickListener(v -> {
            if (listener != null) {
                listener.onApprove(owner);
            }
        });

        holder.btnReject.setOnClickListener(v -> {
            if (listener != null) {
                listener.onReject(owner);
            }
        });

        holder.btnDelete.setOnClickListener(v -> {
            if (listener != null) {
                listener.onDelete(owner);
            }
        });
    }

    @Override
    public int getItemCount() {
        return ownersList.size();
    }

    static class OwnerViewHolder extends RecyclerView.ViewHolder {
        TextView tvTurfName, tvOwnerId, tvOwnerName, tvOwnerMobile, tvBusinessPhone, tvLocation, tvMsme, tvUtilityBill, tvPhotos, tvRouteAccount;
        TextView badgeVerified, badgeSubscription, tvExpiryDate;
        Button btnApprove, btnReject, btnDelete, btnLinkRoute;

        public OwnerViewHolder(@NonNull View itemView) {
            super(itemView);
            tvTurfName = itemView.findViewById(R.id.tvTurfName);
            tvOwnerId = itemView.findViewById(R.id.tvOwnerId);
            tvOwnerName = itemView.findViewById(R.id.tvOwnerName);
            tvOwnerMobile = itemView.findViewById(R.id.tvOwnerMobile);
            tvBusinessPhone = itemView.findViewById(R.id.tvBusinessPhone);
            tvLocation = itemView.findViewById(R.id.tvLocation);
            tvMsme = itemView.findViewById(R.id.tvMsme);
            tvUtilityBill = itemView.findViewById(R.id.tvUtilityBill);
            tvPhotos = itemView.findViewById(R.id.tvPhotos);
            badgeVerified = itemView.findViewById(R.id.badgeVerified);
            badgeSubscription = itemView.findViewById(R.id.badgeSubscription);
            tvExpiryDate = itemView.findViewById(R.id.tvExpiryDate);
            tvRouteAccount = itemView.findViewById(R.id.tvRouteAccount);
            btnApprove = itemView.findViewById(R.id.btnApprove);
            btnReject = itemView.findViewById(R.id.btnReject);
            btnDelete = itemView.findViewById(R.id.btnDelete);
            btnLinkRoute = itemView.findViewById(R.id.btnLinkRoute);
        }
    }
}
