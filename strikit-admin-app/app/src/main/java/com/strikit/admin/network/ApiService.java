package com.strikit.admin.network;

import com.strikit.admin.model.Owner;
import java.util.List;
import retrofit2.Call;
import retrofit2.http.DELETE;
import retrofit2.http.GET;
import retrofit2.http.POST;
import retrofit2.http.Path;
import retrofit2.http.Query;

public interface ApiService {
    @GET("owners")
    Call<List<Owner>> getOwners(@Query("search") String searchQuery);

    @POST("owners/{id}/approve")
    Call<Void> approveOwner(@Path("id") int id);

    @POST("owners/{id}/reject")
    Call<Void> rejectOwner(@Path("id") int id);

    @DELETE("owners/{id}")
    Call<Void> deleteOwner(@Path("id") int id);
}
